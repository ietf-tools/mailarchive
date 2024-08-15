
import os
from .base import *

DATABASES = {
    'default': {
        'HOST': '__DBHOST__',
        'PORT': 5432,
        'NAME': 'datatracker',
        'ENGINE': 'django.db.backends.postgresql',
        'USER': 'django',
        'PASSWORD': 'RkTkDPFnKpko',
    },
}

SECRET_KEY = "__SECRETKEY__"

CELERY_BROKER_URL = '__MQCONNSTR__'

# OIDC configuration
SITE_URL = 'https://__HOSTNAME__'
