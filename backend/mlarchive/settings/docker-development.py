# settings/test.py
import os
from .base import *

ALLOWED_HOSTS = ['*']

DEBUG = True

SERVER_MODE = 'development'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# Blob replication storage for dev
import botocore.config
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

import logging

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}
