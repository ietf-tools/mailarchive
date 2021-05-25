# settings/settings_rebuild.py
from .base import *

HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'mlarchive.archive.backends.custom.ConfigurableElasticSearchEngine',
        'URL': 'http://127.0.0.1:9200/',
        'INDEX_NAME': 'mail-archive-02',
    },
}
