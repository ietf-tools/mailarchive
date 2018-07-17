# settings/development.py
from .base import *

DEBUG = True

DATA_ROOT = '/a/mailarch/data'

# DJANGO DEBUG TOOLBAR SETTINGS
INSTALLED_APPS.append('debug_toolbar')
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
INTERNAL_IPS = get_secret('INTERNAL_IPS')
DEBUG_TOOLBAR_CONFIG = {'INSERT_BEFORE': '<!-- debug_toolbar_here -->'}

DATA_UPLOAD_MAX_NUMBER_FIELDS = 3500

# HAYSTACK SETTINGS
# BaseSignalProcessor does not update the index
# RealtimeSignalProccessor updates the index immediately
# HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.BaseSignalProcessor'
# HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_XAPIAN_PATH = os.path.join(DATA_ROOT, 'xapian.stub')
HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.xapian_backend.XapianEngine',
        'PATH': HAYSTACK_XAPIAN_PATH,
    },
}

# ARCHIVE SETTINGS
ARCHIVE_HOST_URL = 'http://mailarchivetest.ietf.org'
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
CONSOLE_STATS_FILE = os.path.join(DATA_ROOT, 'log', 'console.json')
LOG_FILE = os.path.join(DATA_ROOT, 'log', 'mlarchive.log')
SERVER_MODE = 'development'
STATIC_MODE_ENABLED = True


LOGGING['handlers']['watched_file']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = os.path.join(DATA_ROOT, 'log', 'archive-mail.log')


# DATATRACKER API
DATATRACKER_PERSON_ENDPOINT = 'http://deva.amsl.com/api/v2/person/person'
