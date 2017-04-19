# settings/development.py
from .base import *

DEBUG=True

DATA_ROOT = '/a/mailarch/data'

#CACHES = {
#    'default': {
#        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
#        'LOCATION': 'test-cache'
#    }
#}

# HAYSTACK SETTINGS
# BaseSignalProcessor does not update the index
# RealtimeSignalProccessor updates the index immediately
#HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.BaseSignalProcessor'
#HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_XAPIAN_PATH = os.path.join(DATA_ROOT,'xapian.stub')
HAYSTACK_CONNECTIONS['default']['PATH'] = HAYSTACK_XAPIAN_PATH

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
CONSOLE_STATS_FILE = os.path.join(DATA_ROOT,'log','console.json')
LOG_FILE = os.path.join(DATA_ROOT,'log','mlarchive.log')
SERVER_MODE = 'development'

LOGGING['handlers']['watched_file']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = os.path.join(DATA_ROOT,'log','archive-mail.log')


