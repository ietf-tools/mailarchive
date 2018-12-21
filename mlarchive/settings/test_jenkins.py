# settings/test.py
from .test import *

DATABASES['default']['TEST']['NAME'] = 'jenkins_mailarch'
HAYSTACK_CONNECTIONS['default']['INDEX_NAME'] = 'jenkins-mail-archive'
