# Copyright The IETF Trust 2026, All Rights Reserved
import datetime
import io
from hashlib import sha384

import pytest
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.base import ContentFile, File
from django.core.files.storage import storages
from django.test import override_settings

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage import backfill_stored_objects
from mlarchive.archive.storage_utils import move_object, store_str
from mlarchive.archive.tasks import (
    BACKFILL_STORED_OBJECTS_STOP_KEY, backfill_stored_objects_task)
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
    make_untracked_blob('ml-templates', 'skipped.html')
    second = make_untracked_blob('ml-messages-private', 'secret/two')
    third = make_untracked_blob(BUCKET, 'acme/three')

    result = backfill_stored_objects(batch_size=1)
    assert result == {'last_pk': first.pk, 'created': 1, 'skipped': 0}

    result = backfill_stored_objects(start_after_pk=result['last_pk'], batch_size=1)
    assert result == {'last_pk': second.pk, 'created': 1, 'skipped': 0}

    result = backfill_stored_objects(start_after_pk=result['last_pk'], batch_size=1)
    assert result == {'last_pk': third.pk, 'created': 1, 'skipped': 0}

    assert backfill_stored_objects(start_after_pk=result['last_pk'], batch_size=1) is None
    assert StoredObject.objects.count() == 3
    assert StoredObject.objects.get(store='ml-messages-private', name='secret/two')


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
