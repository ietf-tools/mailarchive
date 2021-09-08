# settings/settings_rebuild.py
from .base import *

# ELASTICSEARCH SETTINGS
ELASTICSEARCH_INDEX_NAME = 'mail-archive-02'
ELASTICSEARCH_SILENTLY_FAIL = True
ELASTICSEARCH_CONNECTION = {
    'URL': 'http://127.0.0.1:9200/',
    'INDEX_NAME': 'mail-archive-02',
}
