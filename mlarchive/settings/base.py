# Django settings for mlarchive project.

import os
import json

from django.core.exceptions import ImproperlyConfigured
from mlarchive import __version__

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# THE ONE TRUE WAY
# JSON-based secrets module
with open(os.path.join(BASE_DIR, "settings", "secrets.json")) as f:
    secrets = json.loads(f.read())


def get_secret(setting, secrets=secrets):
    """Get the secret variable or return explicit exception."""
    try:
        return secrets[setting]
    except KeyError:
        error_msg = "Set the {0} environment variable".format(setting)
        raise ImproperlyConfigured(error_msg)


SECRET_KEY = get_secret("SECRET_KEY")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': get_secret("DATABASES_NAME"),
        'USER': get_secret("DATABASES_USER"),
        'PASSWORD': get_secret("DATABASES_PASSWORD"),
        'OPTIONS': {'charset': 'utf8mb4'},
        'TEST': {
            'CHARSET': 'utf8mb4'
        }
    }
}

DEBUG = False

ALLOWED_HOSTS = ['.ietf.org', '.amsl.com']
ADMINS = (
    ('Ryan Cross', 'rcross@amsl.com'),
)

MANAGERS = ADMINS

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/Los_Angeles'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1
USE_TZ = False

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale
USE_L10N = True

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
MEDIA_URL = ''

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
# ADMIN_MEDIA_PREFIX = '/media/'

# List of callables that know how to import templates from various sources.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR + '/templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # Insert your TEMPLATE_CONTEXT_PROCESSORS here or use this
                # list if you haven't customized them:
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

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'mlarchive.urls'

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',
    'django.contrib.humanize',
    'bootstrap4',
    'celery_haystack',
    'haystack',
    'htauth',
    'mlarchive.archive.apps.ArchiveConfig',
    'widget_tweaks',
]

STATIC_URL = '/static/%s/' % __version__
STATIC_ROOT = os.path.abspath(BASE_DIR + "/../static/%s/" % __version__)

# Additional locations of static files (in addition to each app's static/ dir)
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'externals/static'),
)


# HAYSTACK SETTINGS
HAYSTACK_DEFAULT_OPERATOR = 'AND'
HAYSTACK_SIGNAL_PROCESSOR = 'celery_haystack.signals.CelerySignalProcessor'
HAYSTACK_SEARCH_RESULTS_PER_PAGE = 40

HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'mlarchive.archive.backends.custom.ConfigurableElasticSearchEngine',
        'URL': 'http://127.0.0.1:9200/',
        'INDEX_NAME': 'mail-archive',
    },
}

ELASTICSEARCH_INDEX_MAPPINGS = {
    "django_ct": {'type': 'keyword'},           # "archive.message"
    "django_id": {'type': 'long'},              # primary key of message
    "date": {"type": "date"},
    "email_list": {"type": "keyword"},
    "email_list_exact": {"type": "keyword"},    # can this be an alias?
    "frm": {"type": "text"},
    # "frm_exact": {"type": "keyword"},         # don't need this, faceting on frm_name
    "frm_name": {"type": "keyword"},
    "frm_name_exact": {"type": "keyword"},      # can this be an alias?
    "from": {"type": "alias", "path": "frm"},   # make this an alias of frm to use as search keyword
    "id": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
    # "id": {"type": "keyword"},                # combo of django_ct + django_id e.g. archive.message.1
    "msgid": {"type": "keyword"},
    # "msgid_exact": {"type": "keyword"},       # don't need
    "spam_score": {"type": "integer"},
    "subject": {"type": "text"},
    "subject_base": {"type": "keyword"},        # for sorting on subject
    "base_subject": {"type": "alias", "path": "subject_base"},
    "tdate": {"type": "date"},
    "text": {"type": "text"},
    "tid": {"type": "long"},
    # "to": {"type": "text"},                   # get rid of this
    "torder": {"type": "long"}
}

# ARCHIVE SETTINGS
ARCHIVE_HOST_URL = 'https://mailarchive.ietf.org'
DATA_ROOT = '/a/mailarch/data'
ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
CONSOLE_STATS_FILE = os.path.join(DATA_ROOT, 'log/console.json')
EXPORT_LIMIT = 5000             # maximum number of messages we will export
ANONYMOUS_EXPORT_LIMIT = 100    # maximum number of messages a non-logged in user can export
FILTER_CUTOFF = 5000            # maximum results for which we'll provide filter options
LOG_DIR = '/var/log/mail-archive'
LOG_FILE = os.path.join(LOG_DIR, 'mlarchive.log')
MAILMAN_DIR = '/usr/lib/mailman'
SERVER_MODE = 'production'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
# number of messages to load when scrolling search results
SEARCH_SCROLL_BUFFER_SIZE = HAYSTACK_SEARCH_RESULTS_PER_PAGE
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
    'SpamLevelSpamInspector': {'includes': ['rfc-dist', 'rfc-interest', 'httpbisa', 'ipp', 'krb-wg']}
}

# AUTH
LOGIN_REDIRECT_URL = '/arch/'
AUTHENTICATION_BACKENDS = ('htauth.backend.HtauthBackend',)
HTAUTH_PASSWD_FILENAME = get_secret("HTAUTH_PASSWD_FILENAME")

# Cache settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
        'TIMEOUT': 300,
    }
}

CACHE_MIDDLEWARE_KEY_PREFIX = 'arch'
CACHE_MIDDLEWARE_ALIAS = 'disk'

# Celery Settings
CELERY_BROKER_URL = 'amqp://'
# CELERY_RESULT_BACKEND = 'amqp://'
CELERY_TIMEZONE = 'America/Los_Angeles'
CELERY_ENABLE_UTC = True
CELERY_HAYSTACK_DEFAULT_ALIAS = 'default'
CELERY_HAYSTACK_MAX_RETRIES = 1
CELERY_HAYSTACK_RETRY_DELAY = 300
CELERY_HAYSTACK_TRANSACTION_SAFE = False

# Use one or the other:
# REMOTE_BACKUP_DIR for local backup directory
# REMOTE_BACKUP_COMMAND to run external backup command

# REMOTE_BACKUP_COMMAND = '/a/mailarch/scripts/remote_backup.sh'
# REMOTE_BACKUP_DIR = os.path.join(DATA_ROOT,'archive_backup')

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT, 'export')
# NOTIFY_LIST_CHANGE_COMMAND = '/a/mailarch/scripts/call_imap_import.sh'

# new in Django 1.6
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# DATATRACKER API
DATATRACKER_PERSON_ENDPOINT = 'https://datatracker.ietf.org/api/v2/person/person'
DATATRACKER_PERSON_ENDPOINT_API_KEY = get_secret('DATATRACKER_PERSON_ENDPOINT_API_KEY')

# CLOUDFLARE  INTEGRATION
USING_CDN = False
CLOUDFLARE_AUTH_EMAIL = get_secret("CLOUDFLARE_AUTH_EMAIL")
CLOUDFLARE_AUTH_KEY = get_secret("CLOUDFLARE_AUTH_KEY")
CLOUDFLARE_ZONE_ID = get_secret("CLOUDFLARE_ZONE_ID")
CACHE_CONTROL_MAX_AGE = 60 * 60 * 24 * 7     # one week


###########
# LOGGING #
###########

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
        'archive-mail_file_handler':
        {
            'level': 'DEBUG',
            'formatter': 'simple',
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': os.path.join(LOG_DIR, 'archive-mail.log'),
        }
    },
    'loggers': {
        # Top level logger
        'mlarchive': {
            'handlers': ['mlarchive'],
            'level': 'INFO',
            'propagate': False,
        },
        # Custom logger, e.g. bin scripts, change handler to log to different file
        'mlarchive.custom': {
            'handlers': ['mlarchive'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'haystack': {
            'handlers': ['mlarchive'],
            'level': 'INFO',
            'propagate': False,
        }
    }
}
