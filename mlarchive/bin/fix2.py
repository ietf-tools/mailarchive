#!/usr/bin/python
'''
Fix unindented Received lines.

Based on a short survey we are assuming Received lines immediately follow
envelope.  We use the "From:" header to signify done reading Received lines.
'''
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings'
# -------------------------------------------------------------------------------------

from mlarchive.archive.models import *
from email.utils import parseaddr
import glob
import mailbox
import re

def main():
    REC_HEADER = re.compile(r'(Received: |\s)')
    ANY_HEADER = re.compile(r'[a-zA-Z\-]+:\s')
    ENV_HEADER = re.compile(r'From .*@.* .{24}')
    with open('/a/home/rcross/tmp/fix2.txt') as f:
        files = f.read().splitlines()

    #files = ('/a/www/ietf-mail-archive/text/policy/1999-04.mail',)
    for file in files:
        with open(file) as f:
            count = 0
            inheader = True
            curblank = False
            for line in f:
                count += 1
                if count == 1:  # skip first line
                    continue
                lastblank = curblank
                if line == '\n':
                    curblank = True
                else:
                    curblank = False

                if ENV_HEADER.match(line) and lastblank:
                    inheader = True
                    continue
                if REC_HEADER.match(line):
                    continue
                if ANY_HEADER.match(line):
                    inheader = False
                    continue
                if inheader:
                    print "%s:%s:%s" % (file,count,line)

if __name__ == "__main__":
    main()
