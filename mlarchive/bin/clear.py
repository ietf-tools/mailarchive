#!/usr/bin/python

# Standalone script to reset database

from django.core.management import setup_environ, call_command
from mlarchive import settings

setup_environ(settings)

import subprocess

name = settings.DATABASES['default']['NAME']
user = settings.DATABASES['default']['USER']
passwd = settings.DATABASES['default']['PASSWORD']

# drop and create database
print "Dropping and creating database: %s" % name
mysql_cmd = "'drop database %s; create database %s character set utf8;'" % name 
cmd = [ 'mysql', '--user={0}'.format(user), '--password={0}'.format(passwd), '-e', mysql_cmd ]
subprocess.call(cmd)

# sync
call_command('syndb',noinput=True)
