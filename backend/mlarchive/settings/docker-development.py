# settings/test.py
import os
from .base import *

ALLOWED_HOSTS = ['*']

DEBUG = True

SERVER_MODE = 'development'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

import logging

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}
