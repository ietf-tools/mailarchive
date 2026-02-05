import pytest

from django.core.files.storage import storages

from mlarchive.archive.storage_utils import get_unique_blob_name


@pytest.mark.django_db(transaction=True)
def test_get_unique_blob_name(client):
    bucket = 'ml-messages-incoming'
    prefix = 'testlist.private.'
    blob_name = get_unique_blob_name(prefix=prefix, bucket=bucket)
    storage = storages[bucket]
    assert blob_name.startswith(prefix)
    assert not storage.exists(blob_name)
