# settings/noindex.py
from .base import *

# Identical to production.py but without updates to the index


ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.BaseSignalProcessor'
