# settings/test.py
from .test import *


# HAYSTACK SETTINGS
HAYSTACK_CONNECTIONS['default']['ENGINE'] = 'mlarchive.archive.backends.ConfigurableElasticSearchEngine'
HAYSTACK_CONNECTIONS['default']['URL'] = 'http://127.0.0.1:9200/'
