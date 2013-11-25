'''
Special settings file for running tests.  Set entry in pytest.ini to use this
alternate settings file when running tests:

DJANGO_SETTINGS_MODULE = mlarchive.settings_test
'''
from mlarchive.settings import *

ARCHIVE_DIR = '/tmp/archive/'
