import pytest

from django.core.files.storage import storages

from mlarchive.archive.storage_utils import (get_unique_blob_name, store_str, move_object,
    exists_in_storage)


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
