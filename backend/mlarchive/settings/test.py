# settings/test.py
#
# The only test settings, used in the dev container and in CI. Values that
# differ between those environments (database password, Elasticsearch host)
# come from environment variables, read here or in base.py; CI sets them in
# .github/workflows/tests.yml. Everything that affects behaviour is fixed
# here, so tests behave the same everywhere.
import os
from .base import *

# not env('DATA_ROOT'): a developer's .env points it at real data
DATA_ROOT = '/tmp/mailarch/data'
SECRET_KEY = SECRET_KEY or 'fake-key'

TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# Disable ROUTERS to use one default database for all tables during tests
DATABASE_ROUTERS = []

DATABASES = {
    'default': {
        'HOST': 'db',
        'PORT': 5432,
        'NAME': 'mailarchive',
        'ENGINE': 'django.db.backends.postgresql',
        'USER': 'mailarchive',
        'PASSWORD': env('DATABASES_PASSWORD'),
    },
}

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# BLOBDB
BLOBDB_DATABASE = 'default'

# Off so blob writes never queue a Celery task: there is no broker in CI, and
# locally .env points at a real one
BLOBDB_REPLICATION['ENABLED'] = False

# Blob replication storage for testing
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

# ELASTICSEARCH SETTINGS
# base.py builds the connection from ELASTICSEARCH_HOST and ELASTICSEARCH_PASSWORD
ELASTICSEARCH_INDEX_NAME = 'test-mail-archive'
ELASTICSEARCH_SILENTLY_FAIL = True
ELASTICSEARCH_CONNECTION = {**ELASTICSEARCH_CONNECTION, 'INDEX_NAME': ELASTICSEARCH_INDEX_NAME}
ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.RealtimeSignalProcessor'

# use standard default of 20 as it's easier to test
ELASTICSEARCH_RESULTS_PER_PAGE = 20
SEARCH_RESULTS_PER_PAGE = 20
SEARCH_SCROLL_BUFFER_SIZE = SEARCH_RESULTS_PER_PAGE

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
STATIC_INDEX_DIR = os.path.join(DATA_ROOT, 'static')

SERVER_MODE = 'development'

# log to the console, which pytest captures, rather than to a file
LOGGING['loggers']['mlarchive']['handlers'] = ['console']
del(LOGGING['loggers']['mlarchive.custom'])
del(LOGGING['handlers']['mlarchive'])

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT, 'export')

# CLOUDFLARE  INTEGRATION
USING_CDN = False
