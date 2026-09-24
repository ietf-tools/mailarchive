# Copyright The IETF Trust 2026, All Rights Reserved
import datetime
import logging
from hashlib import sha384

import pytest
from unittest.mock import patch

from django.core.files.storage import storages

from mlarchive.archive.models import StoredObject
from mlarchive.archive.stored_object_reconciliation import (
    DriftReport, audit_list_objects, reconcile_bucket, reconcile_stored_objects)
from mlarchive.archive.storage_utils import store_str
from mlarchive.archive.tasks import reconcile_stored_objects_task
from mlarchive.blobdb.models import Blob
from mlarchive.blobdb.storage import BlobFile
from factories import EmailListFactory, MessageFactory, store_message_blob


BUCKET = 'ml-messages'
CONTENT = b'These are my bytes.'


def digest(content):
    return sha384(content).hexdigest()


def make_untracked_blob(bucket, name, content=CONTENT, modified=None):
    """Create a Blob directly, bypassing the storage, as the historical corpus did."""
    defaults = {'content': content}
    if modified is not None:
        defaults['modified'] = modified
    blob, _ = Blob.objects.update_or_create(bucket=bucket, name=name, defaults=defaults)
    return blob


CLEAN = {
    'rows': 0, 'objects': 0, 'missing': 0, 'untracked': 0, 'tombstoned': 0,
    'lingering': 0, 'mismatched': 0, 'repaired': 0,
}


def test_reconcile_rejects_unknown_bucket():
    with pytest.raises(ValueError):
        reconcile_bucket('ml-nonsense')


@pytest.mark.django_db
def test_reconcile_clean_bucket_finds_no_drift():
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    storage.save('acme/two', BlobFile(content=b'other bytes'))
    storage.save('acme/gone', BlobFile(content=CONTENT))
    storage.delete('acme/gone')

    assert reconcile_bucket(BUCKET) == CLEAN | {'rows': 2, 'objects': 2}


@pytest.mark.django_db
def test_reconcile_tombstones_live_row_without_bytes():
    """Bytes removed behind the storage's back leave a live row that must be tombstoned."""
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    Blob.objects.get(bucket=BUCKET, name='acme/one').delete()

    stats = reconcile_bucket(BUCKET)
    assert stats == CLEAN | {'rows': 1, 'missing': 1}
    assert StoredObject.objects.get(store=BUCKET, name='acme/one').deleted is None

    stats = reconcile_bucket(BUCKET, repair=True)
    assert stats == CLEAN | {'rows': 1, 'missing': 1, 'repaired': 1}
    assert StoredObject.objects.get(store=BUCKET, name='acme/one').deleted is not None

    assert reconcile_bucket(BUCKET) == CLEAN


@pytest.mark.django_db
def test_reconcile_logs_every_missing_row_as_error(caplog):
    """Lost bytes are an incident, so they are reported in full and at ERROR."""
    storage = storages[BUCKET]
    for i in range(3):
        storage.save(f'acme/lost{i}', BlobFile(content=CONTENT))
        Blob.objects.get(bucket=BUCKET, name=f'acme/lost{i}').delete()

    with patch('mlarchive.archive.stored_object_reconciliation.RECONCILE_SAMPLE_LIMIT', 1):
        reconcile_bucket(BUCKET)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].getMessage() == (
        'reconcile ml-messages: 3 live rows with no bytes: acme/lost0, acme/lost1, acme/lost2')


@pytest.mark.django_db
def test_reconcile_refuses_to_tombstone_above_threshold(caplog):
    storage = storages[BUCKET]
    for i in range(3):
        storage.save(f'acme/lost{i}', BlobFile(content=CONTENT))
        Blob.objects.get(bucket=BUCKET, name=f'acme/lost{i}').delete()

    stats = reconcile_bucket(BUCKET, repair=True, batch_size=1, max_missing_repairs=2)

    assert stats == CLEAN | {'rows': 3, 'missing': 3}
    assert StoredObject.objects.filter(store=BUCKET).exclude_deleted().count() == 3
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert messages == [
        'reconcile ml-messages: 3 live rows with no bytes: acme/lost0, acme/lost1, acme/lost2',
        'reconcile ml-messages: 3 live rows with no bytes exceeds max_missing_repairs=2; '
        'left live for investigation',
    ]

    stats = reconcile_bucket(BUCKET, repair=True, batch_size=1, max_missing_repairs=3)
    assert stats == CLEAN | {'rows': 3, 'missing': 3, 'repaired': 3}
    assert not StoredObject.objects.filter(store=BUCKET).exclude_deleted().exists()


@pytest.mark.django_db
def test_reconcile_missing_report_is_capped_above_threshold(caplog):
    """Past the threshold only one name more than the limit is listed, plus the remainder."""
    storage = storages[BUCKET]
    for i in range(4):
        storage.save(f'acme/lost{i}', BlobFile(content=CONTENT))
        Blob.objects.get(bucket=BUCKET, name=f'acme/lost{i}').delete()

    reconcile_bucket(BUCKET, max_missing_repairs=1)

    assert ('reconcile ml-messages: 4 live rows with no bytes: acme/lost0, acme/lost1 '
            '... and 2 more') in caplog.text


@pytest.mark.django_db
def test_reconcile_indexes_untracked_object():
    modified = datetime.datetime(2020, 2, 2, 2, 2, 2, tzinfo=datetime.timezone.utc)
    blob = make_untracked_blob(BUCKET, 'acme/untracked', modified=modified)

    stats = reconcile_bucket(BUCKET)
    assert stats == CLEAN | {'objects': 1, 'untracked': 1}
    assert not StoredObject.objects.exists()

    stats = reconcile_bucket(BUCKET, repair=True)
    assert stats == CLEAN | {'objects': 1, 'untracked': 1, 'repaired': 1}
    record = StoredObject.objects.get(store=BUCKET, name='acme/untracked')
    assert record.sha384 == blob.checksum == digest(CONTENT)
    assert record.len == len(CONTENT)
    assert record.store_created == record.created == record.modified == modified
    assert record.deleted is None

    assert reconcile_bucket(BUCKET) == CLEAN | {'rows': 1, 'objects': 1}


@pytest.mark.django_db
def test_reconcile_refreshes_mismatched_row():
    """Bytes rewritten behind the storage's back leave the row's digest stale."""
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    original = StoredObject.objects.get(store=BUCKET, name='acme/one')
    changed = b'These bytes were rewritten directly.'
    blob = Blob.objects.get(bucket=BUCKET, name='acme/one')
    blob.content = changed
    blob.modified = datetime.datetime.now(datetime.timezone.utc)
    blob.save()

    stats = reconcile_bucket(BUCKET)
    assert stats == CLEAN | {'rows': 1, 'objects': 1, 'mismatched': 1}

    stats = reconcile_bucket(BUCKET, repair=True)
    assert stats == CLEAN | {'rows': 1, 'objects': 1, 'mismatched': 1, 'repaired': 1}
    record = StoredObject.objects.get(store=BUCKET, name='acme/one')
    assert record.pk == original.pk
    assert record.sha384 == digest(changed)
    assert record.len == len(changed)
    assert record.modified == blob.modified > original.modified
    assert record.store_created == original.store_created

    assert reconcile_bucket(BUCKET) == CLEAN | {'rows': 1, 'objects': 1}


@pytest.mark.django_db
def test_reconcile_finds_no_drift_after_overwrite_through_storage():
    """Rewriting an object through the storage is not drift.

    ml-messages-json blobs are overwritten on every neighbouring import, so if the
    checksum column lagged the content the reconcile would report the whole day's
    imports as mismatched rows and, on repair, copy the stale digests into them.
    """
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    changed = b'These bytes were rewritten through the storage.'
    storage.save('acme/one', BlobFile(content=changed))

    assert reconcile_bucket(BUCKET) == CLEAN | {'rows': 1, 'objects': 1}
    record = StoredObject.objects.get(store=BUCKET, name='acme/one')
    assert record.sha384 == digest(changed)
    assert record.len == len(changed)


@pytest.mark.django_db
def test_reconcile_revives_tombstone_when_bytes_were_rewritten():
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    storage.delete('acme/one')
    original = StoredObject.objects.get(store=BUCKET, name='acme/one')
    assert original.deleted is not None
    changed = b'Back again via a bulk path.'
    make_untracked_blob(BUCKET, 'acme/one', content=changed)

    stats = reconcile_bucket(BUCKET)
    assert stats == CLEAN | {'objects': 1, 'tombstoned': 1}

    stats = reconcile_bucket(BUCKET, repair=True)
    assert stats == CLEAN | {'objects': 1, 'tombstoned': 1, 'repaired': 1}
    record = StoredObject.objects.get(store=BUCKET, name='acme/one')
    assert record.pk == original.pk
    assert record.deleted is None
    assert record.sha384 == digest(changed)
    assert record.len == len(changed)
    assert record.modified > original.modified

    assert reconcile_bucket(BUCKET) == CLEAN | {'rows': 1, 'objects': 1}


@pytest.mark.django_db
def test_reconcile_reports_but_keeps_tombstone_over_older_bytes():
    """Bytes older than the tombstone are a delete in progress or its debris, not a revival."""
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    storage.delete('acme/one')
    record = StoredObject.objects.get(store=BUCKET, name='acme/one')
    make_untracked_blob(
        BUCKET, 'acme/one', modified=record.deleted - datetime.timedelta(seconds=1))

    stats = reconcile_bucket(BUCKET, repair=True)
    assert stats == CLEAN | {'objects': 1, 'lingering': 1}
    assert StoredObject.objects.get(store=BUCKET, name='acme/one').deleted == record.deleted


@pytest.mark.django_db
def test_reconcile_batches_and_stays_within_bucket():
    storage = storages[BUCKET]
    for i in range(3):
        storage.save(f'acme/tracked{i}', BlobFile(content=CONTENT))
    for i in range(3):
        make_untracked_blob(BUCKET, f'acme/untracked{i}')
    Blob.objects.get(bucket=BUCKET, name='acme/tracked1').delete()
    make_untracked_blob('ml-messages-private', 'secret/untracked')
    storages['ml-messages-removed'].save('acme/tracked0', BlobFile(content=CONTENT))
    Blob.objects.get(bucket='ml-messages-removed', name='acme/tracked0').delete()

    stats = reconcile_bucket(BUCKET, repair=True, batch_size=2)
    assert stats == CLEAN | {
        'rows': 3, 'objects': 5, 'missing': 1, 'untracked': 3, 'repaired': 4}
    assert StoredObject.objects.filter(store=BUCKET).exclude_deleted().count() == 5
    assert not StoredObject.objects.filter(store='ml-messages-private').exists()
    assert StoredObject.objects.get(
        store='ml-messages-removed', name='acme/tracked0').deleted is None

    assert reconcile_bucket(BUCKET, batch_size=2) == CLEAN | {'rows': 5, 'objects': 5}


@pytest.mark.django_db
def test_reconcile_logs_sampled_drift(caplog):
    for i in range(4):
        make_untracked_blob(BUCKET, f'acme/u{i}')

    # pytest.ini sets log_level = ERROR; raise it here, in the call phase, not in a fixture
    caplog.set_level(logging.WARNING)
    with patch('mlarchive.archive.stored_object_reconciliation.RECONCILE_SAMPLE_LIMIT', 2):
        reconcile_bucket(BUCKET)

    assert 'reconcile ml-messages: 4 objects with no row: acme/u0, acme/u1 ... and 2 more' \
        in caplog.text


def test_drift_report_samples_across_batches(caplog):
    report = DriftReport('demo', sample_limit=3)
    report.add('things', ['a', 'b'])
    report.add('things', ['c', 'd'])
    report.add('nothing', [])
    caplog.set_level(logging.WARNING)
    report.log()

    assert caplog.text.count('reconcile demo') == 1
    assert 'reconcile demo: 4 things: a, b, c ... and 1 more' in caplog.text


@pytest.mark.django_db
def test_reconcile_progress_lines_are_throttled(caplog):
    """At the default interval a short run logs only the per-pass done lines."""
    storage = storages[BUCKET]
    for i in range(3):
        storage.save(f'acme/msg{i}', BlobFile(content=CONTENT))
    caplog.set_level(logging.INFO)

    reconcile_bucket(BUCKET, batch_size=1)

    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert not [m for m in infos if ' so far, ' in m]
    assert len([m for m in infos if m.startswith('reconcile ml-messages rows: 3 in ')]) == 1
    assert len([m for m in infos if m.startswith('reconcile ml-messages objects: 3 in ')]) == 1


@pytest.mark.django_db
def test_reconcile_progress_reports_count_and_cursor(caplog):
    """With the throttle off, every batch logs its running count and name cursor."""
    storage = storages[BUCKET]
    for i in range(3):
        storage.save(f'acme/msg{i}', BlobFile(content=CONTENT))
    caplog.set_level(logging.INFO)

    with patch('mlarchive.archive.stored_object_reconciliation.RECONCILE_PROGRESS_INTERVAL', 0):
        reconcile_bucket(BUCKET, batch_size=2)

    progress = [r.getMessage() for r in caplog.records if ' so far, ' in r.getMessage()]
    assert [m.split(', at ')[1] for m in progress] == [
        'acme/msg1', 'acme/msg2', 'acme/msg1', 'acme/msg2']
    assert progress[0].startswith('reconcile ml-messages rows: 2 so far, ')
    assert progress[1].startswith('reconcile ml-messages rows: 3 so far, ')
    assert progress[2].startswith('reconcile ml-messages objects: 2 so far, ')
    assert progress[3].startswith('reconcile ml-messages objects: 3 so far, ')


@pytest.mark.django_db
def test_reconcile_task_logs_errors(caplog):
    with patch('mlarchive.archive.tasks.reconcile_stored_objects',
               side_effect=RuntimeError('boom')) as reconcile:
        reconcile_stored_objects_task(bucket=BUCKET, repair=True)

    reconcile.assert_called_once_with(
        bucket=BUCKET, repair=True, batch_size=5000, max_missing_repairs=100)
    assert 'Error in reconcile_stored_objects_task: boom' in caplog.text


@pytest.mark.django_db
def test_reconcile_task_forwards_every_parameter():
    with patch('mlarchive.archive.tasks.reconcile_stored_objects') as reconcile:
        reconcile_stored_objects_task(
            bucket=BUCKET, repair=True, batch_size=7, max_missing_repairs=3)

    reconcile.assert_called_once_with(
        bucket=BUCKET, repair=True, batch_size=7, max_missing_repairs=3)


@pytest.mark.django_db(transaction=True)
def test_audit_list_objects():
    elist = EmailListFactory.create(name='acme')
    stored = MessageFactory.create(email_list=elist)
    store_message_blob(stored, b'stored message')
    lost = MessageFactory.create(email_list=elist)
    other = EmailListFactory.create(name='acme-wg')
    MessageFactory.create(email_list=other, hashcode=lost.hashcode)
    store_str('ml-messages', 'acme/orphanhash', content='no message owns me')
    store_str('ml-messages', 'acme-wg/otherorphan', content='different list')
    store_str('ml-messages-removed', 'acme/removedhash', content='different bucket')

    only_messages, only_objects = audit_list_objects(elist)

    assert only_messages == {lost.hashcode.rstrip('=')}
    assert only_objects == {'orphanhash'}


@pytest.mark.django_db(transaction=True)
def test_audit_list_objects_private_list():
    elist = EmailListFactory.create(name='secret', private=True)
    message = MessageFactory.create(email_list=elist)
    store_message_blob(message, b'private message')
    store_str('ml-messages', 'secret/publicorphan', content='wrong bucket')

    assert audit_list_objects(elist) == (set(), set())


@pytest.mark.django_db(transaction=True)
def test_reconcile_stored_objects(caplog):
    public = EmailListFactory.create(name='acme')
    private = EmailListFactory.create(name='secret', private=True)
    for elist in (public, private):
        message = MessageFactory.create(email_list=elist)
        store_message_blob(message, b'stored message')
    lost = MessageFactory.create(email_list=public)
    store_str('ml-messages', 'acme/orphan', content='no message')
    # bytes written behind the storage's back, in a bucket no list uses
    Blob.objects.update_or_create(
        bucket='ml-messages-spam', name='acme/spam', defaults={'content': b'spam'})

    caplog.set_level(logging.INFO)
    stats = reconcile_stored_objects()

    assert 'reconcile_stored_objects: starting, repair=False, buckets=ml-messages, ' in caplog.text
    assert 'reconcile lists: 2 in ' in caplog.text
    assert stats['rows'] == 3
    assert stats['objects'] == 4
    assert stats['untracked'] == 1
    assert stats['repaired'] == 0
    assert stats['lists'] == 2
    assert stats['list_mismatches'] == 1
    assert stats['only_messages'] == 1
    assert stats['only_objects'] == 1
    assert not StoredObject.objects.filter(store='ml-messages-spam').exists()

    stats = reconcile_stored_objects(repair=True)
    assert stats['untracked'] == 1
    assert stats['repaired'] == 1
    assert StoredObject.objects.get(store='ml-messages-spam', name='acme/spam').deleted is None

    stats = reconcile_stored_objects()
    assert stats['rows'] == 4
    assert stats['untracked'] == 0
    assert stats['only_messages'] == 1
    assert lost.hashcode.rstrip('=') not in [
        name.split('/')[1] for name in StoredObject.objects.values_list('name', flat=True)]


@pytest.mark.django_db(transaction=True)
def test_reconcile_stored_objects_single_bucket():
    public = EmailListFactory.create(name='acme')
    private = EmailListFactory.create(name='secret', private=True)
    MessageFactory.create(email_list=public)
    MessageFactory.create(email_list=private)
    store_str('ml-messages-private', 'secret/orphan', content='x')

    stats = reconcile_stored_objects(bucket='ml-messages-private')
    assert stats['rows'] == 1
    assert stats['lists'] == 1
    assert stats['only_messages'] == 1
    assert stats['only_objects'] == 1

    stats = reconcile_stored_objects(bucket='ml-messages-json')
    assert stats['rows'] == 0
    assert stats['lists'] == 0

    with pytest.raises(ValueError):
        reconcile_stored_objects(bucket='ml-nonsense')
