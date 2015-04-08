#!/usr/bin/python
"""
Script to scan through archive of mbox files and produce a spam report.
"""
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.production'
# -------------------------------------------------------------------------------------

from django.conf import settings
#from mlarchive.archive.management.commands import _classes
from mlarchive.bin.scan_utils import get_messages

import argparse
import email
import logging
import shutil
import subprocess
from StringIO import StringIO

progname = sys.argv[0]

from django.utils.log import getLogger
import logging.config
logging.config.dictConfig(settings.LOGGING)
logger = getLogger('mlarchive.custom')

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        os.chmod(path,02777)

def main():
    parser = argparse.ArgumentParser(description='Scan archive for spam.')
    parser.add_argument('path')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    #parser.add_argument('-c','--check',help="check only, dont't import",action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        parser.error('{} must be a directory'.format(args.path))

    fullnames = [ os.path.join(args.path,n) for n in os.listdir(args.path) ]
    elists = filter(os.path.isdir,fullnames)

    for elist in elists:
        total = 0
        spam = 0

        for msg in get_messages(elist):
            total += 1

            # scan
            p = subprocess.Popen(['spamc','-c'], stdin=subprocess.PIPE)
            p.communicate(input=msg.as_string())
            if p.returncode != 0:
                # the message is spam
                spam += 1
                if args.verbose:
                    print "%s: spam" % elist

        # print stats
        print "{}, {}:{}".format(os.path.basename(elist),total,spam)

if __name__ == "__main__":
    main()
