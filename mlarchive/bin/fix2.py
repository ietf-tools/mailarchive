#!/usr/bin/python
'''
Fix unindented Received lines.

Based on a short survey we are assuming Received lines immediately follow
envelope.  We use the "From:" header to signify done reading Received lines.


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
    PATTERN = re.compile(r'^[a-zA-Z\-]+: ')
    with open('/a/home/rcross/tmp/fix2.txt') as f:
        files = f.read().splitlines()
        
    #files = ('/a/www/ietf-mail-archive/text/policy/1999-04.mail',)
    for file in files:
        mb = mailbox.mbox(file)
        for m in mb:
            count = 0
            for line in m.as_string().splitlines():
                count += 1
                if line.startswith('Received: ') or line.startswith(' '):
                    continue
                if PATTERN.match(line):
                    break
                print "%s:%s:%s" % (file,count,line)
        mb.close()
        
if __name__ == "__main__":
    main()
