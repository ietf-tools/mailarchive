import pytest

from django.core.files.storage import storages

import datetime
from hashlib import sha384

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage_utils import (get_unique_blob_name, store_str, move_object,
    exists_in_storage, list_names, remove_from_storage, get_metadata, find_by_checksum,
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
def test_list_names_prefix_is_exact():
    """Neighbouring lists that share a prefix stay out: dns/ is not dns-x/ or dnsop/."""
    for name in ['dns/a', 'dns/b', 'dns-x/a', 'dnsop/a', 'dn/a', 'dns0/a']:
        store_str('ml-messages', name, content='x')
    store_str('ml-messages-private', 'dns/private', content='x')

    assert list(list_names('ml-messages', prefix='dns/')) == ['dns/a', 'dns/b']
    assert list(list_names('ml-messages', prefix='dns')) == [
        'dns-x/a', 'dns/a', 'dns/b', 'dns0/a', 'dnsop/a']
    assert list(list_names('ml-messages-private', prefix='dns/')) == ['dns/private']
    assert list(list_names('ml-messages', prefix='nothing/')) == []


@pytest.mark.django_db
def test_list_names_skips_deleted_and_other_stores():
    store_str('ml-messages', 'acme/kept', content='x')
    store_str('ml-messages', 'acme/gone', content='x')
    remove_from_storage('ml-messages', 'acme/gone')
    store_str('ml-messages-removed', 'acme/removed', content='x')

    assert list(list_names('ml-messages')) == ['acme/kept']
    assert list(list_names('ml-messages-removed')) == ['acme/removed']


def test_list_names_rejects_unknown_kind():
    with pytest.raises(NotImplementedError):
        list_names('ml-nonsense')


def test_list_names_rejects_empty_prefix():
    with pytest.raises(ValueError):
        list_names('ml-messages', prefix='')


@pytest.mark.django_db
def test_list_names_modified_before():
    cutoff = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    store_str('ml-messages', 'acme/old', content='x')
    store_str('ml-messages', 'acme/new', content='x')
    store_str('ml-messages', 'acme/old-gone', content='x')
    StoredObject.objects.filter(name__in=['acme/old', 'acme/old-gone']).update(
        modified=cutoff - datetime.timedelta(days=1))
    remove_from_storage('ml-messages', 'acme/old-gone')

    assert list(list_names('ml-messages', modified_before=cutoff)) == ['acme/old']
    assert list(list_names('ml-messages', prefix='acme/', modified_before=cutoff)) == ['acme/old']
    assert list(list_names('ml-messages')) == ['acme/new', 'acme/old']


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
