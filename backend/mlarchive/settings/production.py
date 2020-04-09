# settings/production.py
from .base import *

# -------------------------------------
# DJANGO SETTINGS
# -------------------------------------

DEBUG = False

ALLOWED_HOSTS = ['.ietf.org', '.amsl.com']
ADMINS = (('Ryan Cross', 'rcross@amsl.com'))


# -------------------------------------
# CUSTOM SETTINGS
# -------------------------------------

# CLOUDFLARE  INTEGRATION
USING_CDN = True
CLOUDFLARE_AUTH_EMAIL = get_secret("CLOUDFLARE_AUTH_EMAIL")
CLOUDFLARE_AUTH_KEY = get_secret("CLOUDFLARE_AUTH_KEY")
CLOUDFLARE_ZONE_ID = get_secret("CLOUDFLARE_ZONE_ID")