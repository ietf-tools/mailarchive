# Django settings for mlarchive project.

import django.conf.global_settings as DEFAULT_SETTINGS
import os
import json
from django.core.exceptions import ImproperlyConfigured

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
        'NAME': 'mailarch',
        'TEST_NAME': 'mailarch_test',
        'USER': get_secret("DATABASES_USER"),
        'PASSWORD': get_secret("DATABASES_PASSWORD"),
        'HOST': '',
        'PORT': '',
    }
}

DEBUG = False
TEMPLATE_DEBUG = False

ALLOWED_HOSTS = ['.ietf.org']
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
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

TEMPLATE_CONTEXT_PROCESSORS = DEFAULT_SETTINGS.TEMPLATE_CONTEXT_PROCESSORS + (
    'django.core.context_processors.request',
    'mlarchive.context_processors.server_mode',
    'mlarchive.context_processors.revision_info',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'mlarchive.urls'

TEMPLATE_DIRS = (
    BASE_DIR + '/templates',
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    #'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',
    'haystack',
    'celery_haystack',
    'mlarchive.archive',
    'htauth',
)

STATIC_URL = '/static/'
STATIC_DOC_ROOT = BASE_DIR + '../static'

###########
# LOGGING #
###########

MY_LOG_FILENAME = '/a/mailarch/data/log/mlarchive.log'
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
            'filename' :   MY_LOG_FILENAME, # full path works
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

HAYSTACK_XAPIAN_PATH = '/a/mailarch/data/archive_index'
HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.xapian_backend.XapianEngine',
        'PATH': '/a/mailarch/data/archive_index',
    },
}

# ARCHIVE SETTINGS
ARCHIVE_DIR = '/a/mailarch/data/archive'
CONSOLE_STATS_FILE = '/a/mailarch/data/log/console.json'
EXPORT_LIMIT = 50000        # maximum number of messages we will export
FILTER_CUTOFF = 15000       # maximum results for which we'll provide filter options
LOG_FILE = '/a/mailarch/data/log/mlarchive.log'
MAILMAN_DIR = '/usr/lib/mailman'
SERVER_MODE = 'production'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
TEST_DATA_DIR = BASE_DIR + '/archive/fixtures'
USE_EXTERNAL_PROCESSOR = False

# spam_score bits
MARK_BITS = { 'NON_ASCII_HEADER':0b0001,
              'NO_RECVD_DATE':0b0010,
              'NO_MSGID':0b0100,
              'HAS_HTML_PART':0b1000 }

# MARK Flags.  0 = disabled.  Otherwise use unique integer
MARK_HTML = 10
MARK_LOAD_SPAM = 11

# AUTH
LOGIN_REDIRECT_URL = '/arch/'
AUTHENTICATION_BACKENDS = (
    'htauth.backend.HtauthBackend',
    )

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

