#!/usr/bin/python
'''
This script handles loading multiple archives
'''
import sys
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast')
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast/mlarchive')

from django.core.management import setup_environ
from django.db.utils import IntegrityError
from mlarchive import settings

setup_environ(settings)

from django.core.management import call_command
import glob
import os

for fil in glob.glob('/a/www/ietf-mail-archive/text/16ng/*.mail'):
    call_command('load', fil, test=True)
