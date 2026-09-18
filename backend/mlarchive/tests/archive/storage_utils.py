import datetime
from hashlib import sha384

import pytest

from django.core.files.storage import storages

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage_utils import (get_unique_blob_name, store_str, move_object,
    exists_in_storage, remove_from_storage, get_metadata, find_by_checksum,
    StoredObjectMetadata)


@pytest.mark.django_db(transaction=True)
def test_get_unique_blob_name(client):
    bucket = 'ml-messages-incoming'
    prefix = 'testlist.private.'
    blob_name = get_unique_blob_name(prefix=prefix, bucket=bucket)
    storage = storages[bucket]
    assert blob_name.startswith(prefix)
    assert not storage.exists(blob_name)


@pytest.mark.django_db(transaction=True)
def test_move_object(client):
    source = 'ml-messages'
    target = 'ml-messages-removed'
    key = 'acme/PjjZawcPwvGsK6zLLOc4DOVwA4w'
    store_str(source, key, content='This is a test')
    assert exists_in_storage(source, key)
    assert not exists_in_storage(target, key)
    move_object(key, source, target)
    assert not exists_in_storage(source, key)
    assert exists_in_storage(target, key)


@pytest.mark.django_db
def test_get_metadata():
    store_str('ml-messages', 'acme/one', content='hello')
    record = StoredObject.objects.get(store='ml-messages', name='acme/one')

    metadata = get_metadata('ml-messages', 'acme/one')
    assert metadata == StoredObjectMetadata(
        store='ml-messages', name='acme/one', sha384=sha384(b'hello').hexdigest(), len=5,
        store_created=record.store_created, modified=record.modified)
    assert get_metadata('ml-messages', 'acme/none') is None
    assert get_metadata('ml-messages-removed', 'acme/one') is None

    remove_from_storage('ml-messages', 'acme/one')
    assert get_metadata('ml-messages', 'acme/one') is None


@pytest.mark.django_db
def test_find_by_checksum():
    digest = sha384(b'same bytes').hexdigest()
    store_str('ml-messages-incoming', 'apple.public.abc', content='same bytes')
    store_str('ml-messages', 'apple/hash1', content='same bytes')
    store_str('ml-messages-removed', 'banana/hash2', content='same bytes')
    store_str('ml-messages-private', 'cherry/hash3', content='same bytes')
    store_str('ml-messages', 'apple/other', content='other bytes')
    remove_from_storage('ml-messages-private', 'cherry/hash3')

    assert find_by_checksum(digest) == [
        ('ml-messages', 'apple/hash1'),
        ('ml-messages-incoming', 'apple.public.abc'),
        ('ml-messages-removed', 'banana/hash2'),
    ]
    assert find_by_checksum(digest, exclude_kinds=('ml-messages-incoming', 'ml-messages-json')) == [
        ('ml-messages', 'apple/hash1'),
        ('ml-messages-removed', 'banana/hash2'),
    ]
    assert find_by_checksum(sha384(b'nothing has this').hexdigest()) == []


@pytest.mark.django_db
def test_metadata_lookups_validate_kind_with_blobstorage_disabled(settings):
    """The kill switch hides the index but does not hide a bad kind."""
    store_str('ml-messages', 'acme/kept', content='x')
    digest = sha384(b'x').hexdigest()
    settings.ENABLE_BLOBSTORAGE = False

    assert get_metadata('ml-messages', 'acme/kept') is None
    assert find_by_checksum(digest) == []
    with pytest.raises(NotImplementedError):
        get_metadata('ml-nonsense', 'acme/kept')
    with pytest.raises(NotImplementedError):
        find_by_checksum(digest, exclude_kinds=('ml-nonsense',))
