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
from optparse import OptionParser
from StringIO import StringIO

import ast
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
# MAIN
# --------------------------------------------------

def main():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-f", "--full", help="perform import of entire archive",
                      action="store_true", default=False)
    parser.add_option("-m", "--mini", help="perform import of one list",
                      action="store_true", default=False)
    parser.add_option("-t", "--test", help="test mode",
                      action="store_true", default=False)
    (options, args) = parser.parse_args()

    stats = {}
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

        if 'text-secure' in path:
            private = True
        else:
            private = False

        # save output from command so we can aggregate statistics
        content = StringIO()
        call_command('load', path, listname=os.path.basename(dir), summary=True,
                     test=options.test, private=private, firstrun=firstrun, stdout=content)

        # gather stats from output
        content.seek(0)
        output = content.read()
        results = ast.literal_eval(output)
        for key,val in results.items():
            stats[key] = stats.get(key,0) + val

    elapsed_time = int(time.time() - start_time)
    print 'Messages Pocessed: %d' % stats['count']
    print 'Errors: %d' % stats['errors']
    print 'Elapsed Time: %s' % str(datetime.timedelta(seconds=elapsed_time))

if __name__ == "__main__":
    main()
