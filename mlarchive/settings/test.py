# settings/test.py
import os
from .base import *

DATA_ROOT = '/tmp/mailarch/data'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_CONNECTIONS['default']['INDEX_NAME'] = 'test-mail-archive'


# use standard default of 20 as it's easier to test
HAYSTACK_SEARCH_RESULTS_PER_PAGE = 20
SEARCH_SCROLL_BUFFER_SIZE = HAYSTACK_SEARCH_RESULTS_PER_PAGE

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
STATIC_INDEX_DIR = os.path.join(DATA_ROOT, 'static')
LOG_FILE = os.path.join(BASE_DIR, 'tests/tmp', 'mlarchive.log')
IMPORT_LOG_FILE = os.path.join(BASE_DIR, 'tests/tmp', 'archive-mail.log')

SERVER_MODE = 'development'

LOGGING['handlers']['mlarchive']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = IMPORT_LOG_FILE

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT, 'export')


# CLOUDFLARE  INTEGRATION
USING_CDN = False