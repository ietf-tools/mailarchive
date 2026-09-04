# Copyright The IETF Trust 2026, All Rights Reserved
import datetime
import io
import logging
from hashlib import sha384

import pytest
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.base import ContentFile, File
from django.core.files.storage import storages
from django.test import override_settings

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage import (
    DriftReport, backfill_stored_objects, reconcile_bucket)
from mlarchive.archive.storage_utils import move_object, store_str
from mlarchive.archive.tasks import (
    BACKFILL_STORED_OBJECTS_STOP_KEY, backfill_stored_objects_task,
    reconcile_stored_objects_task)
from mlarchive.blobdb.models import Blob
from mlarchive.blobdb.storage import BlobFile


BUCKET = 'ml-messages'
CONTENT = b'These are my bytes.'


class UnseekableBytesIO(io.BytesIO):
    """Stand-in for content a MetadataFile cannot digest."""

    def seek(self, *args, **kwargs):
        raise AttributeError('unseekable')


def digest(content):
    return sha384(content).hexdigest()


@pytest.mark.django_db
def test_save_records_stored_object():
    """Saving through the storage writes the bytes and a matching StoredObject."""
    storage = storages[BUCKET]
    mtime = datetime.datetime(2025, 3, 17, 1, 2, 3, tzinfo=datetime.timezone.utc)
    storage.save('acme/abc123', BlobFile(
        content=CONTENT, mtime=mtime, content_type='message/rfc822'))

    # content_type and mtime stay on the Blob; StoredObject tracks identity only
    blob = Blob.objects.get(bucket=BUCKET, name='acme/abc123')
    assert blob.content_type == 'message/rfc822'
    assert blob.mtime == mtime

    record = StoredObject.objects.get(store=BUCKET, name='acme/abc123')
    assert record.sha384 == digest(CONTENT)
    assert record.len == len(CONTENT)
    assert record.deleted is None
    assert record.store_created == record.created == record.modified


@pytest.mark.django_db
def test_save_naive_file_records_stored_object():
    """A plain File carries no metadata, so the storage computes the digest itself."""
    storage = storages[BUCKET]
    storage.save('acme/naive', ContentFile(CONTENT))

    record = StoredObject.objects.get(store=BUCKET, name='acme/naive')
    assert record.sha384 == digest(CONTENT)
    assert record.len == len(CONTENT)


@pytest.mark.django_db
def test_resave_identical_content_leaves_modified_alone():
    storage = storages[BUCKET]
    storage.save('acme/abc123', BlobFile(content=CONTENT))
    original = StoredObject.objects.get(store=BUCKET, name='acme/abc123')

    storage.save('acme/abc123', BlobFile(content=CONTENT))
    record = StoredObject.objects.get(store=BUCKET, name='acme/abc123')
    assert record.pk == original.pk
    assert record.modified == original.modified


@pytest.mark.django_db
def test_resave_changed_content_updates_record():
    storage = storages[BUCKET]
    storage.save('acme/abc123', BlobFile(content=CONTENT))
    original = StoredObject.objects.get(store=BUCKET, name='acme/abc123')

    changed = b'These are different bytes entirely.'
    storage.save('acme/abc123', BlobFile(content=changed, content_type='text/plain'))
    record = StoredObject.objects.get(store=BUCKET, name='acme/abc123')
    assert record.pk == original.pk
    assert record.sha384 == digest(changed)
    assert record.len == len(changed)
    assert record.modified > original.modified
    assert record.store_created == original.store_created


@pytest.mark.django_db
def test_delete_tombstones_record():
    storage = storages[BUCKET]
    storage.save('acme/abc123', BlobFile(content=CONTENT))
    storage.delete('acme/abc123')

    assert not Blob.objects.filter(bucket=BUCKET, name='acme/abc123').exists()
    record = StoredObject.objects.get(store=BUCKET, name='acme/abc123')
    assert record.deleted is not None
    assert not StoredObject.objects.exclude_deleted().filter(
        store=BUCKET, name='acme/abc123').exists()


@pytest.mark.django_db
def test_delete_of_untracked_object_is_not_an_error():
    """Objects predating the backfill have no row; reconcile handles that, not delete."""
    storage = storages[BUCKET]
    Blob.objects.update_or_create(
        bucket=BUCKET, name='acme/untracked', defaults={'content': CONTENT})

    storage.delete('acme/untracked')
    assert not Blob.objects.filter(bucket=BUCKET, name='acme/untracked').exists()
    assert not StoredObject.objects.filter(store=BUCKET, name='acme/untracked').exists()


@pytest.mark.django_db
def test_save_after_delete_revives_record():
    storage = storages[BUCKET]
    storage.save('acme/abc123', BlobFile(content=CONTENT))
    original = StoredObject.objects.get(store=BUCKET, name='acme/abc123')
    storage.delete('acme/abc123')

    storage.save('acme/abc123', BlobFile(content=CONTENT))
    record = StoredObject.objects.get(store=BUCKET, name='acme/abc123')
    assert record.pk == original.pk
    assert record.deleted is None
    assert record.store_created == original.store_created


@pytest.mark.django_db
def test_save_survives_metadata_failure(monkeypatch, caplog):
    """Bytes are authoritative: a failed metadata write is logged, not raised."""
    storage = storages[BUCKET]

    def boom(self, name, metadata):
        raise RuntimeError('no metadata for you')

    monkeypatch.setattr(type(storage), '_save_stored_object', boom)
    storage.save('acme/abc123', BlobFile(content=CONTENT))

    assert Blob.objects.filter(bucket=BUCKET, name='acme/abc123').exists()
    assert not StoredObject.objects.filter(store=BUCKET, name='acme/abc123').exists()
    assert 'failed to record its StoredObject' in caplog.text


@pytest.mark.django_db
def test_delete_aborts_when_metadata_fails(monkeypatch):
    """A live row must never outlive its bytes, so a failed tombstone stops the delete."""
    storage = storages[BUCKET]
    storage.save('acme/abc123', BlobFile(content=CONTENT))

    def boom(self, name):
        raise RuntimeError('no tombstone for you')

    monkeypatch.setattr(type(storage), '_delete_stored_object', boom)
    with pytest.raises(RuntimeError):
        storage.delete('acme/abc123')

    assert Blob.objects.filter(bucket=BUCKET, name='acme/abc123').exists()


@pytest.mark.django_db
def test_save_survives_unseekable_content(caplog):
    """Content that cannot be digested is still stored; only the index entry is lost."""
    storage = storages[BUCKET]
    storage.save('acme/unseekable', File(UnseekableBytesIO(CONTENT)))

    blob = Blob.objects.get(bucket=BUCKET, name='acme/unseekable')
    assert bytes(blob.content) == CONTENT
    assert not StoredObject.objects.filter(store=BUCKET, name='acme/unseekable').exists()
    assert 'could not read metadata' in caplog.text


@pytest.mark.django_db(transaction=True)
def test_move_object_tombstones_source_and_records_target():
    source = 'ml-messages'
    target = 'ml-messages-removed'
    key = 'acme/PjjZawcPwvGsK6zLLOc4DOVwA4w'
    store_str(source, key, content='This is a test')
    move_object(key, source, target)

    assert StoredObject.objects.get(store=source, name=key).deleted is not None
    moved = StoredObject.objects.get(store=target, name=key)
    assert moved.deleted is None
    assert moved.sha384 == digest(b'This is a test')


# --------------------------------------------------
# Backfill
# --------------------------------------------------

def make_untracked_blob(bucket, name, content=CONTENT, modified=None):
    """Create a Blob directly, bypassing the storage, as the historical corpus did."""
    defaults = {'content': content}
    if modified is not None:
        defaults['modified'] = modified
    blob, _ = Blob.objects.update_or_create(bucket=bucket, name=name, defaults=defaults)
    return blob


@pytest.mark.django_db
def test_backfill_indexes_untracked_blobs():
    """Pre-existing blobs get rows built from Blob columns alone, with no byte reads."""
    modified = datetime.datetime(2019, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    blob = make_untracked_blob(BUCKET, 'acme/old', modified=modified)
    assert not StoredObject.objects.exists()

    result = backfill_stored_objects()

    assert result == {'last_pk': blob.pk, 'created': 1, 'skipped': 0}
    record = StoredObject.objects.get(store=BUCKET, name='acme/old')
    assert record.sha384 == digest(CONTENT) == blob.checksum
    assert record.len == len(CONTENT)
    assert record.store_created == record.created == record.modified == modified
    assert record.deleted is None


@pytest.mark.django_db
def test_backfill_returns_none_when_nothing_remains():
    assert backfill_stored_objects() is None
    blob = make_untracked_blob(BUCKET, 'acme/old')
    assert backfill_stored_objects(start_after_pk=blob.pk) is None


@pytest.mark.django_db
def test_backfill_leaves_tracked_rows_alone():
    """A row written by the storage may be more accurate than the backfill's guess."""
    storage = storages[BUCKET]
    storage.save('acme/tracked', BlobFile(content=CONTENT))
    original = StoredObject.objects.get(store=BUCKET, name='acme/tracked')
    make_untracked_blob(BUCKET, 'acme/untracked')

    result = backfill_stored_objects()

    assert result['created'] == 1
    assert result['skipped'] == 1
    record = StoredObject.objects.get(store=BUCKET, name='acme/tracked')
    assert record.pk == original.pk
    assert record.modified == original.modified
    assert StoredObject.objects.filter(store=BUCKET, name='acme/untracked').exists()


@pytest.mark.django_db
def test_backfill_is_idempotent():
    make_untracked_blob(BUCKET, 'acme/old')
    backfill_stored_objects()
    result = backfill_stored_objects()
    assert result['created'] == 0
    assert result['skipped'] == 1
    assert StoredObject.objects.count() == 1


@pytest.mark.django_db
def test_backfill_resumes_by_pk_cursor():
    """Each call returns a cursor the next call continues from, across buckets."""
    first = make_untracked_blob(BUCKET, 'acme/one')
    make_untracked_blob('not-a-storage', 'skipped.bin')
    second = make_untracked_blob('ml-messages-private', 'secret/two')
    third = make_untracked_blob('ml-templates', 'message-detail.html')

    result = backfill_stored_objects(batch_size=1)
    assert result == {'last_pk': first.pk, 'created': 1, 'skipped': 0}

    result = backfill_stored_objects(start_after_pk=result['last_pk'], batch_size=1)
    assert result == {'last_pk': second.pk, 'created': 1, 'skipped': 0}

    result = backfill_stored_objects(start_after_pk=result['last_pk'], batch_size=1)
    assert result == {'last_pk': third.pk, 'created': 1, 'skipped': 0}

    assert backfill_stored_objects(start_after_pk=result['last_pk'], batch_size=1) is None
    assert StoredObject.objects.count() == 3
    assert StoredObject.objects.get(store='ml-messages-private', name='secret/two')
    assert StoredObject.objects.get(store='ml-templates', name='message-detail.html')
    assert not StoredObject.objects.filter(store='not-a-storage').exists()


@pytest.mark.django_db
def test_backfill_mixed_bucket_batch():
    """Existence checks are per bucket, so the same name in two stores is two objects."""
    make_untracked_blob(BUCKET, 'acme/same')
    make_untracked_blob('ml-messages-removed', 'acme/same', content=b'other bytes')
    storages['ml-messages-spam'].save('acme/same', BlobFile(content=CONTENT))

    result = backfill_stored_objects()

    assert result['created'] == 2
    assert result['skipped'] == 1
    assert StoredObject.objects.filter(name='acme/same').count() == 3
    assert StoredObject.objects.get(
        store='ml-messages-removed', name='acme/same').sha384 == digest(b'other bytes')


@pytest.fixture
def real_cache():
    """The test settings use DummyCache, which cannot hold the task's stop flag."""
    locmem = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    with override_settings(CACHES=locmem):
        cache.clear()
        yield
        cache.clear()


@pytest.mark.django_db
def test_backfill_task_chains_until_done(real_cache):
    blob = make_untracked_blob(BUCKET, 'acme/old')

    with patch.object(backfill_stored_objects_task, 'apply_async') as apply_async:
        backfill_stored_objects_task(batch_size=1, countdown=7)

    apply_async.assert_called_once_with(
        kwargs={'start_after_pk': blob.pk, 'batch_size': 1, 'countdown': 7},
        countdown=7,
        queue='blobdb',
    )
    assert StoredObject.objects.filter(store=BUCKET, name='acme/old').exists()

    with patch.object(backfill_stored_objects_task, 'apply_async') as apply_async:
        backfill_stored_objects_task(start_after_pk=blob.pk, batch_size=1)
    apply_async.assert_not_called()


@pytest.mark.django_db
def test_backfill_task_honours_stop_flag(real_cache):
    make_untracked_blob(BUCKET, 'acme/old')
    cache.set(BACKFILL_STORED_OBJECTS_STOP_KEY, True, timeout=None)

    with patch.object(backfill_stored_objects_task, 'apply_async') as apply_async:
        backfill_stored_objects_task()

    apply_async.assert_not_called()
    assert not StoredObject.objects.exists()


# --------------------------------------------------
# Reconcile
# --------------------------------------------------

CLEAN = {
    'rows': 0, 'objects': 0, 'missing': 0, 'untracked': 0, 'tombstoned': 0,
    'lingering': 0, 'mismatched': 0, 'repaired': 0,
}


@pytest.mark.django_db
def test_exists_many_returns_present_subset():
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    storage.save('acme/two', BlobFile(content=CONTENT))
    storages['ml-messages-removed'].save('acme/three', BlobFile(content=CONTENT))

    assert storage.exists_many(['acme/one', 'acme/two', 'acme/three', 'acme/none']) == {
        'acme/one', 'acme/two'}
    assert storage.exists_many([]) == set()


@pytest.mark.django_db
def test_inventory_pages_through_store_without_byte_reads():
    storage = storages[BUCKET]
    modified = datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc)
    first = make_untracked_blob(BUCKET, 'acme/one', modified=modified)
    second = make_untracked_blob(BUCKET, 'acme/two', content=b'other bytes')
    make_untracked_blob('ml-messages-removed', 'acme/elsewhere')

    page, cursor = storage.inventory(limit=1)
    assert page == [('acme/one', digest(CONTENT), len(CONTENT), modified)]
    assert cursor == first.pk

    page, cursor = storage.inventory(after=cursor, limit=1)
    assert page == [('acme/two', digest(b'other bytes'), len(b'other bytes'), second.modified)]
    assert cursor == second.pk

    assert storage.inventory(after=cursor, limit=1) == ([], None)


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

    with patch('mlarchive.archive.storage.RECONCILE_SAMPLE_LIMIT', 1):
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
    with patch('mlarchive.archive.storage.RECONCILE_SAMPLE_LIMIT', 2):
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
def test_reconcile_task_logs_errors(caplog):
    with patch('mlarchive.archive.tasks.reconcile_stored_objects',
               side_effect=RuntimeError('boom')) as reconcile:
        reconcile_stored_objects_task(bucket=BUCKET, repair=True)

    reconcile.assert_called_once_with(bucket=BUCKET, repair=True)
    assert 'Error in reconcile_stored_objects_task: boom' in caplog.text
