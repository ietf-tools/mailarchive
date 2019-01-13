# settings/noindex.py
from .base import *

# Identical to production.py but without updates to the index

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.BaseSignalProcessor'
