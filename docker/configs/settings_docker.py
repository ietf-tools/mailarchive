# settings/settings_rebuild.py
from .base import *

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.RealtimeSignalProcessor'

