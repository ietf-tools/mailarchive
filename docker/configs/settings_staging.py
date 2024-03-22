# settings/settings_staging.py
from .base import *

from mlarchive import __version__
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIC_URL = "https://static.ietf.org/mailarchive/%s/"%__version__
STATIC_ROOT = os.path.abspath(BASE_DIR + "/../../static/")

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.CelerySignalProcessor'
