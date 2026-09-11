# Copyright The IETF Trust 2026, All Rights Reserved
import pytest

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured


def check_artifact_storages():
    apps.get_app_config('archive').check_artifact_storages()


def test_artifact_storages_match_their_aliases():
    """The shipped settings satisfy the invariant the code relies on."""
    check_artifact_storages()


def test_artifact_storage_alias_must_equal_bucket_name(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        'ml-messages': {
            'BACKEND': 'mlarchive.archive.storage.StoredObjectBlobdbStorage',
            'OPTIONS': {'bucket_name': 'some-other-bucket'},
        },
    }
    with pytest.raises(ImproperlyConfigured, match="ml-messages \\(bucket_name='some-other-bucket'\\)"):
        check_artifact_storages()


def test_artifact_storage_names_must_exist_in_storages(settings):
    settings.ARTIFACT_STORAGE_NAMES = settings.ARTIFACT_STORAGE_NAMES + ['ml-nonsense']
    with pytest.raises(ImproperlyConfigured, match='ml-nonsense'):
        check_artifact_storages()
