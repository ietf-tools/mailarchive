#!/usr/bin/python
'''
This is a utility script that handles loading multiple archives
Use "-f" to load entire archive, otherwise the script uses the
subset of lists defined in SUBSET below.

NOTE: this was built for running the initial import of the archive.
Therefore it calls load with firstrun=True.  Never do this after
the initial import, becase message that aren't in the legacy archive
will be considered spam.

to run first do
export DJANGO_SETTINGS_MODULE=mlarchive.settings
'''
import sys
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast')
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast/mlarchive')

#from django.core.management import setup_environ
from django.core.management.base import CommandError
from django.db.utils import IntegrityError
#from mlarchive import settings
from django.conf import settings

#setup_environ(settings)

from django.core.management import call_command
from mlarchive.archive.management.commands._classes import ListError
from optparse import OptionParser
from StringIO import StringIO

import datetime
import gc
import glob
import re
import os
import time

# --------------------------------------------------
# Globals
# --------------------------------------------------
ALL = sorted(glob.glob('/a/www/ietf-mail-archive/text*/*'))
FILE_PATTERN = re.compile(r'^\d{4}-\d{2}(|.mail)$')
SOURCE_DIR = '/a/www/ietf-mail-archive/'
SUBSET = ('abfab','alto','ancp','autoconf','bliss','ccamp','cga-ext','codec','dane','dmm','dnsop',
          'dime','discuss','emu','gen-art','grow','hipsec','homenet','i2rs','ietf82-team',
          'ietf83-team','ietf84-team','ipsec','netconf','sip','simple')
MINI = ('yang',)
# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def get_format(filename):
    '''
    Function to determine the type of mailbox file whose filename is provided.
    mmdf: starts with 4 control-A's
    mbox: starts with "From "
    '''
    with open(filename) as f:
        line = f.readline()
        if line == '\x01\x01\x01\x01\n':
            return 'mmdf'
        elif line.startswith('From '):
            return 'mbox'

def is_empty(filename):
    '''
    Takes a filename as string.  Returns true if file is empty
    '''
    statinfo = os.stat(filename)
    if statinfo.st_size == 0:
        return True
    else:
        return False
# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-f", "--full", help="perform import of entire archive",
                      action="store_true", default=False)
    parser.add_option("-t", "--test", help="test mode",
                      action="store_true", default=False)
    parser.add_option("-m", "--mini", help="perform import of one list",
                      action="store_true", default=False)
    (options, args) = parser.parse_args()

    total_count = 0
    error_count = 0
    firstrun = False
    start_time = time.time()

    if options.full:
        dirs = ALL
        firstrun = True
    elif options.mini:
        dirs = [ x for x in ALL if os.path.basename(x) in MINI ]
    else:
        dirs = [ x for x in ALL if os.path.basename(x) in SUBSET ]

    for dir in dirs:
        print 'Loading: %s' % dir
        mboxs = [ f for f in os.listdir(dir) if FILE_PATTERN.match(f) ]

        # we need to import the files in chronological order so thread resolution works
        sorted_mboxs = sorted(mboxs)

        # exclude directories
        full = [ os.path.join(dir,x) for x in sorted_mboxs ]
        files = filter(os.path.isfile,full)

        for path in files:
            if is_empty(path):
                continue
            format = get_format(path)
            if 'text-secure' in path:
                private = True
            else:
                private = False

            # save output from command so we can aggregate statistics
            content = StringIO()
            call_command('load', path, format=format, listname=os.path.basename(dir),
                         test=options.test, private=private, firstrun=firstrun, stdout=content)

            # gather stats from output
            content.seek(0)
            output = content.read()
            parts = output.split(':')
            total_count += int(parts[2])
            error_count += int(parts[3])

    elapsed_time = time.time() - start_time
    print 'Messages Pocessed: %d' % total_count
    print 'Errors: %d' % error_count
    print 'Elapsed Time: %s' % str(datetime.timedelta(seconds=elapsed_time))


if __name__ == "__main__":
    main()
