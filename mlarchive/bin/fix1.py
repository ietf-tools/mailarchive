#!/usr/bin/python
'''
>From quote, "From" lines that occur in the middle of a message


to run first do
export DJANGO_SETTINGS_MODULE=mlarchive.settings
'''

import sys
sys.path.insert(0, '/a/home/rcross/src/amsl/mailarch/trunk')
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast/mlarchive')

from django.core.management import setup_environ
from django.db.utils import IntegrityError
from mlarchive import settings

setup_environ(settings)

from mlarchive.archive.models import *
from email.utils import parseaddr
import glob
import mailbox
import re

def main():
    PATTERN = re.compile(r'From .*@.* .{24}')
    with open('/a/home/rcross/tmp/fix1.txt') as f:
        files = f.read().splitlines()
        
    for file in files:
        with open(file) as f:
            for line in f:
                if line.startswith('From '):
                    if not PATTERN.match(line):
                        print line
    

if __name__ == "__main__":
    main()
