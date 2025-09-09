# settings/test.py
import os
from .base import *

DATA_ROOT = '/tmp/mailarch/data'

TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# Disable ROUTERS to use one default database for all tables during tests
DATABASE_ROUTERS = []

DATABASES = {
    'default': {
        'HOST': 'db',
        'PORT': 5432,
        'NAME': 'mailarch',
        'ENGINE': 'django.db.backends.postgresql',
        'USER': 'mailarch',
        'PASSWORD': 'franticmarble',
    },
}

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# ELASTICSEARCH SETTINGS
ELASTICSEARCH_INDEX_NAME = 'test-mail-archive'
ELASTICSEARCH_SILENTLY_FAIL = True
ES_URL = 'http://{}:9200/'.format(env('ELASTICSEARCH_HOST'))
ELASTICSEARCH_CONNECTION = {
    'URL': ES_URL,
    'INDEX_NAME': 'test-mail-archive',
    'http_auth': ('elastic', 'changeme'),
}
ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.RealtimeSignalProcessor'

# use standard default of 20 as it's easier to test
ELASTICSEARCH_RESULTS_PER_PAGE = 20
SEARCH_RESULTS_PER_PAGE = 20
SEARCH_SCROLL_BUFFER_SIZE = SEARCH_RESULTS_PER_PAGE

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
STATIC_INDEX_DIR = os.path.join(DATA_ROOT, 'static')
LOG_FILE = os.path.join(BASE_DIR, 'tests/tmp', 'mlarchive.log')

SERVER_MODE = 'development'

LOGGING['handlers']['mlarchive']['filename'] = LOG_FILE

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# BLOBDB
BLOBDB_DATABASE = 'default'

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT, 'export')

# CLOUDFLARE  INTEGRATION
USING_CDN = False
