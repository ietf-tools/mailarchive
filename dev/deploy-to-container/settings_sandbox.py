
import os
from .base import *


DATABASES = {
    'default': {
        'HOST': '__DBHOST__',
        'PORT': 5432,
        'NAME': 'mailarch',
        'ENGINE': 'django.db.backends.postgresql',
        'USER': 'mailarch',
        'PASSWORD': 'franticmarble',
    },
}

SECRET_KEY = "__SECRETKEY__"

CELERY_BROKER_URL = '__MQCONNSTR__'

# OIDC configuration
SITE_URL = 'https://__HOSTNAME__'
