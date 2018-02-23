# settings/test.py
from .base import *

DATA_ROOT = '/tmp/mailarch/data'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# Don't try and create test IETF database
del DATABASES['ietf']

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
#HAYSTACK_CONNECTIONS['default']['ENGINE'] = 'haystack_elasticsearch.elasticsearch5.Elasticsearch5SearchEngine'
HAYSTACK_CONNECTIONS['default']['ENGINE'] = 'mlarchive.archive.backends.ConfigurableElasticSearchEngine'
HAYSTACK_CONNECTIONS['default']['URL'] = 'http://127.0.0.1:9200/'
HAYSTACK_CONNECTIONS['default']['INDEX_NAME'] = 'test'

# use standard default of 20 as it's easier to test
HAYSTACK_SEARCH_RESULTS_PER_PAGE = 20
SEARCH_SCROLL_BUFFER_SIZE = HAYSTACK_SEARCH_RESULTS_PER_PAGE

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
STATIC_INDEX_DIR = os.path.join(DATA_ROOT, 'static')
LOG_FILE = os.path.join(BASE_DIR,'tests/tmp','mlarchive.log')
IMPORT_LOG_FILE = os.path.join(BASE_DIR,'tests/tmp','archive-mail.log')

SERVER_MODE = 'development'

LOGGING['handlers']['watched_file']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = IMPORT_LOG_FILE

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache'
    }
}

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT,'export')

# uncomment to disable filters / facets
#FILTER_CUTOFF = 0

# Inspectors
#INSPECTORS = {
#    'ListIdSpamInspector': {'includes':['mpls']}
#}
