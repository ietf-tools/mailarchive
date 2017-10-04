# settings/development.py
from .base import *

# NOTE: DEBUG must be false for long running message imports
DEBUG=False

DATA_ROOT = '/a/mailarch/data'
STAGING_ROOT = '/a/mailarch/data_staging'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache'
    }
}

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.BaseSignalProcessor'
#HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_XAPIAN_PATH = os.path.join(STAGING_ROOT,'xapian.stub')
HAYSTACK_CONNECTIONS['default']['PATH'] = HAYSTACK_XAPIAN_PATH

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
CONSOLE_STATS_FILE = os.path.join(STAGING_ROOT,'log','console.json')
LOG_FILE = os.path.join(STAGING_ROOT,'log','mlarchive.log')
SERVER_MODE = 'development'

LOGGING['handlers']['watched_file']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = os.path.join(STAGING_ROOT,'log','archive-mail.log')

