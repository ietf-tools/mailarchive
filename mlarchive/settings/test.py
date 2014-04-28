# settings/test.py
from .base import *

ARCHIVE_DIR = '/tmp/mailarch/data/archive/'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'

HAYSTACK_XAPIAN_PATH = '/tmp/mailarch/data/archive_index'
HAYSTACK_CONNECTIONS['default']['PATH'] = HAYSTACK_XAPIAN_PATH

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache'
    }
}
