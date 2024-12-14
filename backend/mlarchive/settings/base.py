"""
Django settings for mlarchive project.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/

Using django-environ
https://github.com/joke2k/django-environ
"""

import json
import os
import sys
import environ
from email.utils import getaddresses

from mlarchive import __version__, __release_hash__


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))

env = environ.Env(
    # set casting, default value
    ADMINS=(list, []),
    ALLOWED_HOSTS=(list, ['*']),
    ANONYMOUS_EXPORT_LIMIT=(int, 100),
    CELERY_BROKER_URL=(str, 'amqp://'),
    CLOUDFLARE_AUTH_EMAIL=(str, ''),
    CLOUDFLARE_AUTH_KEY=(str, ''),
    CLOUDFLARE_ZONE_ID=(str, ''),
    DATA_UPLOAD_MAX_MEMORY_SIZE=(int, 90000000),
    DATA_ROOT=(str, '/data'),
    DATABASES_NAME=(str, 'mailarch'),
    DATABASES_USER=(str, 'mailarch'),
    DATABASES_PASSWORD=(str, ''),
    DATABASES_HOST=(str, ''),
    DATABASES_PORT=(str, ''),
    DATABASES_OPTS_JSON=(str, '{}'),
    DATATRACKER_PERSON_ENDPOINT_API_KEY=(str, ''),
    DEBUG=(bool, False),
    DEBUG_TOOLBAR_ON=(bool, False),
    ELASTICSEARCH_HOST=(str, '127.0.0.1'),
    ELASTICSEARCH_PASSWORD=(str, 'changeme'),
    ELASTICSEARCH_SIGNAL_PROCESSOR=(str, 'mlarchive.archive.signals.CelerySignalProcessor'),
    EXPORT_LIMIT=(int, 5000),
    HTAUTH_PASSWD_FILENAME=(str, ''),
    IMPORT_MESSAGE_APIKEY=(str, ''),
    INTERNAL_IPS=(list, []),
    LOG_DIR=(str, '/var/log/mail-archive'),
    LOG_HANDLERS=(list, ['mlarchive']),
    LOG_LEVEL=(str, 'INFO'),
    MAILMAN_API_PASSWORD=(str, ''),
    MAILMAN_API_URL=(str, 'https://mailman.prod.ietf.org/3.1'),
    MAILMAN_API_USER=(str, ''),
    MAILMAN_CF_ACCESS_CLIENT_ID=(str, ''),
    MAILMAN_CF_ACCESS_CLIENT_SECRET=(str, ''),
    MEMCACHED_SERVICE_HOST=(str, '127.0.0.1'),
    MEMCACHED_SERVICE_PORT=(str, '11211'),
    OIDC_RP_CLIENT_ID=(str, ''),
    OIDC_RP_CLIENT_SECRET=(str, ''),
    SCOUT_MONITOR=(bool, False),
    SCOUT_KEY=(str, ''),
    SCOUT_NAME=(str, 'Mailarchive'),
    SECRET_KEY=(str, ''),
    SERVER_MODE=(str, 'development'),
    STATIC_URL=(str, '/static/'),
    STATIC_FRAG=(str, '/../../static/'),
    USING_CDN=(bool, False),
)

# reading .env file
environ.Env.read_env(os.path.join(ROOT_DIR, '.env'))


# -------------------------------------
# DJANGO SETTINGS
# -------------------------------------

DEBUG = env('DEBUG')
SERVER_MODE = env('SERVER_MODE')
SECRET_KEY = env('SECRET_KEY')
ADMINS = getaddresses(env('ADMINS'))
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
DATA_UPLOAD_MAX_MEMORY_SIZE = env('DATA_UPLOAD_MAX_MEMORY_SIZE')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env("DATABASES_NAME"),
        'USER': env("DATABASES_USER"),
        'PASSWORD': env("DATABASES_PASSWORD"),
        'HOST': env("DATABASES_HOST"),
        'PORT': env("DATABASES_PORT"),
        'OPTIONS': json.loads(env("DATABASES_OPTS_JSON")),
    }
}

SITE_ID = 1

# Timezone
USE_TZ = True
TIME_ZONE = 'UTC'

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/
LANGUAGE_CODE = 'en-us'
USE_I18N = False

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

INTERNAL_IPS = env('INTERNAL_IPS')

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',
    'django.contrib.humanize',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'mozilla_django_oidc',
    'django_bootstrap5',
    'django_celery_beat',
    'mlarchive.archive.apps.ArchiveConfig',
    'widget_tweaks',
]


MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django_referrer_policy.middleware.ReferrerPolicyMiddleware',
    'csp.middleware.CSPMiddleware',
    'mlarchive.middleware.JsonExceptionMiddleware',
]


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR + '/templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                # custom
                'django.template.context_processors.request',
                'mlarchive.context_processors.server_mode',
                'mlarchive.context_processors.revision_info',
                'mlarchive.context_processors.static_mode_enabled',
            ],
        },
    },
]

MEDIA_ROOT = ''

MEDIA_URL = ''

ROOT_URLCONF = 'mlarchive.urls'

STATIC_URL = env('STATIC_URL').format(__version__)
if '{}' in env('STATIC_FRAG'):
    STATIC_FRAG = env('STATIC_FRAG').format(__version__)
else:
    STATIC_FRAG = env('STATIC_FRAG')

STATIC_ROOT = os.path.abspath(BASE_DIR + STATIC_FRAG)

# Additional locations of static files (in addition to each app's static/ dir)
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'externals/static'),
)

TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# -------------------------------------
# CUSTOM SETTINGS
# -------------------------------------

SEARCH_RESULTS_PER_PAGE = 40

# ELASTICSEARCH SETTINGS
ELASTICSEARCH_INDEX_NAME = 'mail-archive'
ELASTICSEARCH_SILENTLY_FAIL = True
ES_URL = 'http://{}:9200/'.format(env('ELASTICSEARCH_HOST'))
ELASTICSEARCH_CONNECTION = {
    'URL': ES_URL,
    'INDEX_NAME': 'mail-archive',
    'http_auth': ('elastic', env('ELASTICSEARCH_PASSWORD')),
}
ELASTICSEARCH_DEFAULT_OPERATOR = 'AND'
ELASTICSEARCH_RESULTS_PER_PAGE = 40
ELASTICSEARCH_SIGNAL_PROCESSOR = env('ELASTICSEARCH_SIGNAL_PROCESSOR')


"""
Elastic field mappings

 use text field for search and keyword fields for sorting, filter, aggregations
 id and url are multifields
 https://www.elastic.co/guide/en/elasticsearch/reference/current/multi-fields.html
"""

ELASTICSEARCH_INDEX_MAPPINGS = {
    'properties': {
        'base_subject': {'type': 'alias', 'path': 'subject_base'},
        'date': {'type': 'date'},
        'django_ct': {'type': 'keyword'},
        'django_id': {'type': 'long'},
        'email_list': {'type': 'keyword'},
        'email_list_exact': {'type': 'keyword'},
        'frm': {'type': 'text'},
        'frm_name': {'type': 'keyword'},
        'frm_name_exact': {'type': 'keyword'},
        'from': {'type': 'alias', 'path': 'frm'},
        'id': {'type': 'text', 'fields': {'keyword': {'type': 'keyword', 'ignore_above': 256}}},
        'msgid': {'type': 'keyword'},
        'spam_score': {'type': 'integer'},
        'subject': {'type': 'text'},
        'subject_base': {'type': 'keyword'},
        'text': {'type': 'text'},
        'thread_date': {'type': 'date'},
        'thread_depth': {'type': 'long'},
        'thread_id': {'type': 'long'},
        'thread_order': {'type': 'long'},
        'url': {'type': 'text', 'fields': {'keyword': {'type': 'keyword', 'ignore_above': 256}}}
    }
}

# SECURITY SETTINGS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# Content security policy configuration (django-csp)
CSP_REPORT_ONLY = False
CSP_DEFAULT_SRC = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", 'data:', 'https://online.swagger.io', 'https://validator.swagger.io', 'https://cdn.datatables.net', 'https://static.ietf.org')
CSP_FONT_SRC = ("'self'", 'data:', 'https://fonts.googleapis.com', 'https://fonts.gstatic.com', 'https://static.ietf.org')
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com', 'https://cdn.datatables.net', 'https://static.ietf.org')
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com', 'https://cdn.datatables.net', 'https://static.ietf.org')
CSP_CONNECT_SRC = ("'self'", 'https://raw.githubusercontent.com')

# Setting for django_referrer_policy.middleware.ReferrerPolicyMiddleware
REFERRER_POLICY = 'strict-origin-when-cross-origin'

# ARCHIVE SETTINGS
ARCHIVE_HOST_URL = 'https://mailarchive.ietf.org'
DATA_ROOT = env('DATA_ROOT')
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
INCOMING_DIR = os.path.join(DATA_ROOT, 'incoming')
ARCHIVE_MBOX_DIR = os.path.join(DATA_ROOT, 'archive_mbox')
CONSOLE_STATS_FILE = os.path.join(DATA_ROOT, 'log', 'console.json')

# maximum number of messages a non-superuser can export
EXPORT_LIMIT = env('EXPORT_LIMIT')
# maximum number of messages a non-authenticated user can export
ANONYMOUS_EXPORT_LIMIT = env('ANONYMOUS_EXPORT_LIMIT')
# maximum results for which we'll provide filter options
FILTER_CUTOFF = 5000

LOG_DIR = env('LOG_DIR')
LOG_FILE = os.path.join(LOG_DIR, 'mlarchive.log')

# MAILMAN SETTINGS
MAILMAN_API_URL = env('MAILMAN_API_URL')
MAILMAN_API_USER = env('MAILMAN_API_USER')
MAILMAN_API_PASSWORD = env('MAILMAN_API_PASSWORD')
MAILMAN_CF_ACCESS_CLIENT_ID = env('MAILMAN_CF_ACCESS_CLIENT_ID')
MAILMAN_CF_ACCESS_CLIENT_SECRET = env('MAILMAN_CF_ACCESS_CLIENT_SECRET')
IMPORT_MESSAGE_APIKEY = env('IMPORT_MESSAGE_APIKEY')

# API KEYS: key=endpoint, value=[api-key,]
API_KEYS = {
    '/api/v1/message/import/': [IMPORT_MESSAGE_APIKEY],
}

# Default timeout for HTTP requests via the requests library
DEFAULT_REQUESTS_TIMEOUT = 20  # seconds

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE = True

# number of messages to load when scrolling search results
SEARCH_SCROLL_BUFFER_SIZE = SEARCH_RESULTS_PER_PAGE
TEST_DATA_DIR = BASE_DIR + '/archive/fixtures'
USE_EXTERNAL_PROCESSOR = False
MAX_THREAD_DEPTH = 6
THREAD_ORDER_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
MIME_TYPES_PATH = os.path.join(BASE_DIR, 'mime.types')

# Static Mode
STATIC_MODE_ENABLED = True
STATIC_INDEX_DIR = os.path.join(DATA_ROOT, 'static')
STATIC_INDEX_MESSAGES_PER_PAGE = 500
STATIC_INDEX_YEAR_MINIMUM = 750

# spam_score bits
MARK_BITS = {'NON_ASCII_HEADER': 0b0001,
             'NO_RECVD_DATE': 0b0010,
             'NO_MSGID': 0b0100,
             'HAS_HTML_PART': 0b1000}

# MARK Flags.  0 = disabled.  Otherwise use unique integer
MARK_HTML = 10
MARK_LOAD_SPAM = 11

# Inspector configuration
INSPECTORS = {
    'ListIdSpamInspector': {'includes': ['rfc-dist', 'rfc-interest', 'ipp', 'krb-wg']},
    'ListIdExistsSpamInspector': {'includes': ['httpbisa']},
    'SpamLevelSpamInspector': {'includes': ['rfc-dist', 'rfc-interest', 'httpbisa', 'ipp', 'krb-wg', 'ietf-dkim']},
    'NoArchiveInspector': {},
    'LongMessageIDSpamInspector': {},
}

# AUTH
LOGIN_REDIRECT_URL = '/arch/'
LOGOUT_REDIRECT_URL = '/arch/'
AUTHENTICATION_BACKENDS = (
    'mozilla_django_oidc.auth.OIDCAuthenticationBackend',
    # 'mlarchive.archive.backends.authbackend.HtauthBackend',
)

HTAUTH_PASSWD_FILENAME = env("HTAUTH_PASSWD_FILENAME")

# Cache settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '{}:{}'.format(env('MEMCACHED_SERVICE_HOST'), env('MEMCACHED_SERVICE_PORT')),
        'TIMEOUT': 300,
    }
}

# Celery Settings
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_TIMEZONE = 'America/Los_Angeles'
CELERY_ENABLE_UTC = True
CELERY_DEFAULT_TASK = 'mlarchive.archive.tasks.CelerySignalHandler'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_HAYSTACK_DEFAULT_ALIAS = 'default'
CELERY_HAYSTACK_MAX_RETRIES = 1
CELERY_HAYSTACK_RETRY_DELAY = 300
CELERY_HAYSTACK_TRANSACTION_SAFE = False


# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT, 'export')
IMPORT_DIR = os.path.join(DATA_ROOT, 'incoming')
# NOTIFY_LIST_CHANGE_COMMAND = '/a/mailarch/scripts/call_imap_import.sh'


# DATATRACKER API
DATATRACKER_PERSON_ENDPOINT = 'https://datatracker.ietf.org/api/v2/person/person'
DATATRACKER_PERSON_ENDPOINT_API_KEY = env('DATATRACKER_PERSON_ENDPOINT_API_KEY')

# CLOUDFLARE  INTEGRATION
USING_CDN = env('USING_CDN')
CLOUDFLARE_AUTH_EMAIL = env("CLOUDFLARE_AUTH_EMAIL")
CLOUDFLARE_AUTH_KEY = env("CLOUDFLARE_AUTH_KEY")
CLOUDFLARE_ZONE_ID = env("CLOUDFLARE_ZONE_ID")
CACHE_CONTROL_MAX_AGE = 60 * 60 * 24 * 7     # one week

# OIDC SETTINGS
OIDC_RP_CLIENT_ID = env('OIDC_RP_CLIENT_ID')
OIDC_RP_CLIENT_SECRET = env('OIDC_RP_CLIENT_SECRET')
OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_RP_SCOPES = 'openid email roles'
# OIDC_RP_IDP_SIGN_KEY = ''
# OIDC_CREATE_USER = False
OIDC_OP_JWKS_ENDPOINT = 'https://auth.ietf.org/api/openid/jwks/'
OIDC_OP_AUTHORIZATION_ENDPOINT = 'https://auth.ietf.org/api/openid/authorize/'
OIDC_OP_TOKEN_ENDPOINT = 'https://auth.ietf.org/api/openid/token/'
OIDC_OP_USER_ENDPOINT = 'https://auth.ietf.org/api/openid/userinfo/'
OIDC_OP_X_END_SESSION_ENDPOINT = 'https://auth.ietf.org/api/openid/end-session/'
OIDC_OP_LOGOUT_URL_METHOD = 'mlarchive.authbackend.oidc.get_logout_url'
OIDC_STORE_ID_TOKEN = True
OIDC_USERNAME_ALGO = 'mlarchive.authbackend.oidc.generate_username'

# DJANGO DEBUG TOOLBAR SETTINGS
if env('DEBUG_TOOLBAR_ON'):
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    DEBUG_TOOLBAR_CONFIG = {'INSERT_BEFORE': '<!-- debug_toolbar_here -->'}

# SCOUTAPM
if SERVER_MODE == 'production':
    INSTALLED_APPS.insert(0, 'scout_apm.django')

SCOUT_MONITOR = env('SCOUT_MONITOR')
SCOUT_KEY = env('SCOUT_KEY')
SCOUT_NAME = env('SCOUT_NAME')
SCOUT_ERRORS_ENABLED = True
SCOUT_SHUTDOWN_MESSAGE_ENABLED = False
SCOUT_REVISION_SHA = __release_hash__[:7]
SCOUT_CORE_AGENT_DIR = '/a/core-agent/1.4.0'
SCOUT_CORE_AGENT_FULL_NAME = 'scout_apm_core-v1.4.0-x86_64-unknown-linux-musl'
SCOUT_CORE_AGENT_DOWNLOAD = False
SCOUT_CORE_AGENT_LAUNCH = False

###########
# LOGGING #
###########

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        'json': {
            "class": "mlarchive.utils.jsonlogger.MailArchiveJsonFormatter",
            "style": "{",
            "format": "{asctime}{levelname}{message}{name}{pathname}{lineno}{funcName}{process}",
        }
    },
    'handlers': {
        'mlarchive':
        {
            'level': 'DEBUG',
            'formatter': 'simple',
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': LOG_FILE,
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
        },
    },
    'loggers': {
        # Top level logger
        'mlarchive': {
            'handlers': env('LOG_HANDLERS'),
            'level': env('LOG_LEVEL'),
            'propagate': False,
        },
        # Custom logger, e.g. bin scripts, change handler to log to different file
        'mlarchive.custom': {
            'handlers': ['mlarchive'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    }
}
