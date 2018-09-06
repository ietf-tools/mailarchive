# settings/test.py
from .test import *


# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_CONNECTIONS['default']['ENGINE'] = 'mlarchive.archive.backends.custom.ConfigurableElasticSearchEngine'
HAYSTACK_CONNECTIONS['default']['URL'] = 'http://127.0.0.1:9200/'
HAYSTACK_CONNECTIONS['default']['INDEX_NAME'] = 'test-mail-archive'
