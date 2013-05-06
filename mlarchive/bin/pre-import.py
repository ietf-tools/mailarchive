#!/usr/bin/python
'''
Find record causing Term too long error in index build


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
    PATTERN = re.compile(r'<!--X-Message-Id:\s+(.*)\s+-->')
    for dir in glob.glob('/a/www/ietf-mail-archive/web*/*/current/'):
        listname = dir.split('/')[-3]
        print "Importing %s" % listname
        for fil in glob.glob(dir + 'msg?????.html'):
            with open(fil) as f:
                found = False
                for line in f:
                    if line.startswith('<!--X-Message-Id:'):
                        match = PATTERN.match(line)
                        if match:
                            found = True
                            msgid = match.groups()[0]
                        else:
                            raise Error('pattern failed (%s)' % fil)
                
                if not found:
                    print "No Message Id: %s" % fil
                else:
                    number = int(os.path.basename(fil)[3:8])
                    Legacy.objects.create(msgid=msgid,email_list_id=listname,number=number)
                
                
if __name__ == "__main__":
    main()
