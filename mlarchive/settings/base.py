# Django settings for mlarchive project.

import django.conf.global_settings as DEFAULT_SETTINGS
import os
import json

from django.core.exceptions import ImproperlyConfigured
from mlarchive import __version__

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# THE ONE TRUE WAY
# JSON-based secrets module
with open(os.path.join(BASE_DIR,"settings","secrets.json")) as f:
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
        'TEST_NAME': get_secret("DATABASES_TEST_NAME"),
        'USER': get_secret("DATABASES_USER"),
        'PASSWORD': get_secret("DATABASES_PASSWORD"),
    },
    'ietf': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': get_secret("IETF_DATABASES_NAME"),
        'USER': get_secret("IETF_DATABASES_USER"),
        'PASSWORD': get_secret("IETF_DATABASES_PASSWORD"),
    }
}

DEBUG = False

ALLOWED_HOSTS = ['.ietf.org','.amsl.com']
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
#ADMIN_MEDIA_PREFIX = '/media/'

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
    'bootstrap3',
    'celery_haystack',
    'haystack',
    'htauth',
    'mlarchive.archive',
    'widget_tweaks',
]

STATIC_URL = '/static/%s/' % __version__
STATIC_ROOT = os.path.abspath(BASE_DIR + "/../static/%s/" % __version__)

# Additional locations of static files (in addition to each app's static/ dir)
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'externals/static'),
)


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
        'watched_file':
        {
            'level' : 'DEBUG',
            'formatter' : 'simple',
            'class' : 'logging.handlers.WatchedFileHandler',
            'filename' :  '/a/mailarch/data/log/mlarchive.log',
        },
        'archive-mail_file_handler':
        {
            'level' : 'DEBUG',
            'formatter' : 'simple',
            'class' : 'logging.handlers.WatchedFileHandler',
            'filename' :   '/a/mailarch/data/log/archive-mail.log',
        },
        'email':
        {
            'level' : 'DEBUG',
            'formatter' : 'simple',
            'class' : 'logging.handlers.SMTPHandler',
            'mailhost' : ('ietfa.amsl.com',25),
            'fromaddr': 'rcross@ietfa.amsl.com',
            'toaddrs': ['rcross@amsl.com'],
            'subject': 'logging message',
        }
    },
    'loggers': {
        'mlarchive.custom': {
            'handlers': ['watched_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'archive-mail': {
            'handlers': ['archive-mail_file_handler'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'mlarchive.email': {
            'handlers': ['email'],
            #'handlers': ['mail_admins'],
            'level': 'DEBUG',
            'propagate': True,
        }
    }
}

# HAYSTACK SETTINGS
HAYSTACK_DEFAULT_OPERATOR = 'AND'
HAYSTACK_SIGNAL_PROCESSOR = 'celery_haystack.signals.CelerySignalProcessor'

HAYSTACK_XAPIAN_PATH = '/a/mailarch/data/xapian.stub'
HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.xapian_backend.XapianEngine',
        'PATH': '/a/mailarch/data/archive_index',
    },
}

# ARCHIVE SETTINGS
DATA_ROOT = '/a/mailarch/data'
ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
CONSOLE_STATS_FILE = os.path.join(DATA_ROOT,'log/console.json')
EXPORT_LIMIT = 50000        # maximum number of messages we will export
FILTER_CUTOFF = 15000       # maximum results for which we'll provide filter options
LOG_FILE = os.path.join(DATA_ROOT,'log/mlarchive.log')
MAILMAN_DIR = '/usr/lib/mailman'
SERVER_MODE = 'production'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SEARCH_SCROLL_BUFFER_SIZE = 20  # number of messages to load when scrolling search results
TEST_DATA_DIR = BASE_DIR + '/archive/fixtures'
USE_EXTERNAL_PROCESSOR = False
MAX_THREAD_DEPTH = 6

# spam_score bits
MARK_BITS = { 'NON_ASCII_HEADER':0b0001,
              'NO_RECVD_DATE':0b0010,
              'NO_MSGID':0b0100,
              'HAS_HTML_PART':0b1000 }

# MARK Flags.  0 = disabled.  Otherwise use unique integer
MARK_HTML = 10
MARK_LOAD_SPAM = 11

# Inspector configuration
INSPECTORS = {
    'ListIdSpamInspector': {'includes':['ietf-dkim']},
    'ListIdExistsSpamInspector': {'includes':['webdav']}
}

# AUTH
LOGIN_REDIRECT_URL = '/arch/'
AUTHENTICATION_BACKENDS = (
    'htauth.backend.HtauthBackend',
    )
HTAUTH_PASSWD_FILENAME = get_secret("HTAUTH_PASSWD_FILENAME")

# Cache settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
        'TIMEOUT': 300,
    }
}

# Celery Settings
BROKER_URL = 'amqp://'
#CELERY_RESULT_BACKEND = 'amqp://'
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
EXPORT_DIR = os.path.join(DATA_ROOT,'export')
# NOTIFY_LIST_CHANGE_COMMAND = '/a/mailarch/scripts/call_imap_import.sh'

# new in Django 1.6
TEST_RUNNER = 'django.test.runner.DiscoverRunner'
