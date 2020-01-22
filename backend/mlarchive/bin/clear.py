#!../../../env/bin/python

# Standalone broilerplate -------------------------------------------------------------
from .django_setup import do_setup
do_setup(django_settings='mlarchive.settings.staging')
# -------------------------------------------------------------------------------------

from django.conf import settings
from django.core.management import call_command
import subprocess

name = settings.DATABASES['default']['NAME']
user = settings.DATABASES['default']['USER']
passwd = settings.DATABASES['default']['PASSWORD']

# drop and create database
print("Dropping and creating database: %s" % name)
mysql_cmd = "drop database {0}; create database {0} character set utf8;".format(name) 
cmd = [ 'mysql', '--user={0}'.format(user), '--password={0}'.format(passwd), '-e', mysql_cmd ]
subprocess.call(cmd)

# sync
call_command('syncdb',interactive=False)
