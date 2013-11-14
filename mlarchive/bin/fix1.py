#!/usr/bin/python
'''
>From quote, "From" lines that occur in the middle of a message
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
    PATTERN = re.compile(r'From .*@.* .{24}')
    with open('/a/home/rcross/tmp/fix1.txt') as f:
        files = f.read().splitlines()

    #files = ('/a/www/ietf-mail-archive/text/policy/1999-04.mail',)
    for file in files:
        with open(file) as f:
            curblank = False
            count = 0
            for line in f:
                count += 1
                lastblank = curblank
                if line == '\n':
                    curblank = True
                else:
                    curblank = False

                if line.startswith('From '):
                    if not PATTERN.match(line) and lastblank:
                        print '%s:%d %s' % (file,count,line)


if __name__ == "__main__":
    main()
