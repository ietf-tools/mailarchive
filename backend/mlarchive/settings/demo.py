# settings/demo.py
#
# Runnable settings for the Nuxt proof-of-concept demo. Like
# docker-development, but — exactly as settings/test.py does — it routes the
# blobdb models to the *default* database (no separate blobdb connection) and
# turns off blob replication, so messages can be loaded and saved without the
# full blob-import pipeline. Uses a dedicated Elasticsearch index so it won't
# clash with a real dev index.
import os
from .base import *  # noqa

ALLOWED_HOSTS = ['*']
DEBUG = True
SERVER_MODE = 'development'
AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

DATABASES = {
    'default': {
        'HOST': env('DATABASES_HOST'),
        'PORT': 5432,
        'NAME': 'mailarchive',
        'ENGINE': 'django.db.backends.postgresql',
        'USER': 'mailarchive',
        'PASSWORD': env('DATABASES_PASSWORD'),
    },
}

# Use one database for everything; no blobdb routing.
DATABASE_ROUTERS = []
BLOBDB_DATABASE = 'default'
BLOBDB_REPLICATION['ENABLED'] = False

# Replication is disabled, but the blobdb app still validates that the r2-*
# replica storages are configured. Define them against the dev minio blobstore
# (same block as settings/test.py and docker-development).
import botocore.config  # noqa: E402

for storagename in ARTIFACT_STORAGE_NAMES:
    replica_storagename = f"r2-{storagename}"
    STORAGES[replica_storagename] = {
        "BACKEND": "mlarchive.archive.storage.MetadataS3Storage",
        "OPTIONS": dict(
            endpoint_url="http://blobstore:9000",
            access_key="minio_root",
            secret_key="minio_pass",
            security_token=None,
            client_config=botocore.config.Config(
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                signature_version="s3v4",
                connect_timeout=BLOB_STORE_CONNECT_TIMEOUT,
                read_timeout=BLOB_STORE_READ_TIMEOUT,
                retries={"total_max_attempts": BLOB_STORE_MAX_ATTEMPTS},
            ),
            verify=False,
            bucket_name=f"{storagename}",
        ),
    }

# ELASTICSEARCH
ELASTICSEARCH_INDEX_NAME = 'demo-mail-archive'
ELASTICSEARCH_SILENTLY_FAIL = True
ELASTICSEARCH_CONNECTION['URL'] = 'http://{}:9200/'.format(env('ELASTICSEARCH_HOST'))
ELASTICSEARCH_CONNECTION['INDEX_NAME'] = ELASTICSEARCH_INDEX_NAME
ELASTICSEARCH_CONNECTION['http_auth'] = ('elastic', 'changeme')
ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.RealtimeSignalProcessor'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}

USING_CDN = False
