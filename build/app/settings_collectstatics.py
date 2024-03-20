from .base import *
from mailarchive import __version__

STATIC_URL = "https://static.ietf.org/ma/%s/"%__version__
STATIC_ROOT = os.path.abspath(BASE_DIR + "/../../static/")
