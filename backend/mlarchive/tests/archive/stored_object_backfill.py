# Copyright The IETF Trust 2026, All Rights Reserved
import datetime
from hashlib import sha384

import pytest
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.storage import storages
from django.test import override_settings

from mlarchive.archive.models import StoredObject
from mlarchive.archive.stored_object_backfill import (
    BACKFILL_STORED_OBJECTS_STOP_KEY, backfill_stored_objects, backfill_stored_objects_task)
from mlarchive.blobdb.models import Blob
from mlarchive.blobdb.storage import BlobFile


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
