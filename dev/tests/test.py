# settings/test.py
import os
from .base import *

DATA_ROOT = '/data'
SECRET_KEY = 'fake-key'

DATABASES = {
    'default': {
        'HOST': 'db',
        'PORT': 5432,
        'NAME': 'mailarchive',
        'ENGINE': 'django.db.backends.postgresql',
        'USER': 'django',
        'PASSWORD': 'RkTkDPFnKpko',
    },
}

TEST_RUNNER = 'django.test.runner.DiscoverRunner'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# ELASTICSEARCH SETTINGS
ELASTICSEARCH_INDEX_NAME = 'test-mail-archive'
ELASTICSEARCH_SILENTLY_FAIL = True
ELASTICSEARCH_CONNECTION['URL'] = 'http://localhost:9200/'
ELASTICSEARCH_CONNECTION['INDEX_NAME'] = ELASTICSEARCH_INDEX_NAME

ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.RealtimeSignalProcessor'

# use standard default of 20 as it's easier to test
ELASTICSEARCH_RESULTS_PER_PAGE = 20
SEARCH_RESULTS_PER_PAGE = 20
SEARCH_SCROLL_BUFFER_SIZE = SEARCH_RESULTS_PER_PAGE

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
STATIC_INDEX_DIR = os.path.join(DATA_ROOT, 'static')
# LOG_FILE = os.path.join(BASE_DIR, 'tests/tmp', 'mlarchive.log')

SERVER_MODE = 'development'

# log to console
LOGGING['loggers']['mlarchive']['handlers'] = ['console']

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT, 'export')


# CLOUDFLARE  INTEGRATION
USING_CDN = False