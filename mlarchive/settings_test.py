'''
Special settings file for running tests.  Set entry in pytest.ini to use this
alternate settings file when running tests:

DJANGO_SETTINGS_MODULE = mlarchive.settings_test
'''
from mlarchive.settings import *

ARCHIVE_DIR = '/tmp/mailarch/data/archive/'

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
#HAYSTACK_USE_REALTIME_SEARCH = True

HAYSTACK_XAPIAN_PATH = '/tmp/mailarch/data/archive_index'
HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.xapian_backend.XapianEngine',
        'PATH': '/tmp/mailarch/data/archive_index',
    },
}

#CACHES = {
#    'default': {
#        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
#    }
#}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache'
    }
}
