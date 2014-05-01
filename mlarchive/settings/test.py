# settings/test.py
from .base import *

DATA_ROOT = '/tmp/mailarch/data'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_XAPIAN_PATH = os.path.join(DATA_ROOT,'archive_index')
HAYSTACK_CONNECTIONS['default']['PATH'] = HAYSTACK_XAPIAN_PATH

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
LOG_FILE = os.path.join(DATA_ROOT,'log','mlarchive.log')
SERVER_MODE = 'development'

LOGGING['handlers']['watched_file']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = os.path.join(DATA_ROOT,'log','archive-mail.log')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache'
    }
}
