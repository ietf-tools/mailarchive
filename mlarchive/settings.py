# Django settings for mlarchive project.

import django.conf.global_settings as DEFAULT_SETTINGS
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


DEBUG = True
TEMPLATE_DEBUG = True

ADMINS = (
    # ('Ryan Cross', 'rcross@amsl.com'),
)

MANAGERS = ADMINS

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/Chicago'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

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

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'ezuvpao6ju9dqpx1555dt$saly@_-rqgjgtvy2_xmfzdvop^+6'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

TEMPLATE_CONTEXT_PROCESSORS = DEFAULT_SETTINGS.TEMPLATE_CONTEXT_PROCESSORS + (
    'django.core.context_processors.request',
    'mlarchive.context_processors.server_mode',
    'mlarchive.context_processors.revision_info',
    'mlarchive.context_processors.facet_info',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'mlarchive.middleware.QueryMiddleware',
)

ROOT_URLCONF = 'mlarchive.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    BASE_DIR + '/templates',
)

# STATIC_URL = 
INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    #'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
     'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    'haystack',
    'mlarchive.archive',
    'htauth',
)

STATIC_URL = '/static/'


###########
# LOGGING #
###########

# taken from conf/global_settings.py.
# in Django 1.5 we can choose to add to (not override) global logging settings

MY_LOG_FILENAME = '/a/home/rcross/data/log/mlarchive.log'
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'rotating_file':
        {
            'level' : 'DEBUG',
            #'formatter' : 'verbose', # from the django doc example
            'class' : 'logging.handlers.TimedRotatingFileHandler',
            'filename' :   MY_LOG_FILENAME, # full path works
            'when' : 'midnight',
            'interval' : 1,
            'backupCount' : 7,
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'mlarchive.custom': {
            'handlers': ['rotating_file'],
            'level': 'DEBUG',
            'propagate': True,
        }
    }
}

# HAYSTACK SETTINGS
#HAYSTACK_SITECONF = 'mlarchive.search_sites'
#HAYSTACK_SEARCH_ENGINE = 'xapian'
HAYSTACK_XAPIAN_PATH = '/a/home/rcross/data/archive_index'
HAYSTACK_USE_REALTIME_SEARCH = True
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'

# ARCHIVE SETTINGS
ARCHIVE_DIR = '/a/home/rcross/data/archive'
SERVER_MODE = 'development'
LOG_FILE = '/a/home/rcross/data/log/mlarchive.log'

LOGIN_REDIRECT_URL = '/archive/'
AUTHENTICATION_BACKENDS = (
    'htauth.backend.HtauthBackend',
    )

# Put SECRET_KEY in here, or any other sensitive or site-specific
# changes.  DO NOT commit settings_local.py to svn.
from settings_local import *
