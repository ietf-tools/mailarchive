# Copyright The IETF Trust 2026, All Rights Reserved
import datetime
import io
from hashlib import sha384

import pytest

from django.core.files.base import ContentFile, File
from django.core.files.storage import storages

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage_utils import move_object, store_str
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
