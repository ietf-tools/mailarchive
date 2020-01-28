#!../../../env/bin/python
"""
Script to scan through archive of mbox files and produce a spam report.
"""
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import email
import logging
import os
import shutil
import subprocess
import sys

from django.conf import settings
from mlarchive.bin.scan_utils import get_messages

progname = sys.argv[0]

from django.utils.log import getLogger
import logging.config
logging.config.dictConfig(settings.LOGGING)
logger = getLogger('mlarchive.custom')

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        os.chmod(path,0o2777)

def main():
    parser = argparse.ArgumentParser(description='Scan archive for spam.')
    parser.add_argument('path')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        parser.error('{} must be a directory'.format(args.path))

    fullnames = [ os.path.join(args.path,n) for n in os.listdir(args.path) ]
    elists = list(filter(os.path.isdir,fullnames))

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
                    print("%s: spam" % elist)

        # print stats
        print("{}, {}:{}".format(os.path.basename(elist),total,spam))

if __name__ == "__main__":
    main()
