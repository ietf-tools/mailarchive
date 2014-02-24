#!/usr/bin/python
"""
Script to load messages that were excluded from the initial import.  Takes one
positional argument, the path to the "spam" directory of files to load.  First
spamc is used to determine if the message is spam.

~/.spamassassin/user_prefs can be used to override global rules.  For instance:

score FH_DATE_IS_19XX 0.1   # lower score of two digit date

"""
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings'
# -------------------------------------------------------------------------------------

from django.conf import settings
from mlarchive.archive.management.commands import _classes

import argparse
import email
import logging
import shutil
import subprocess

progname = sys.argv[0]

from django.utils.log import getLogger
import logging.config
logging.config.dictConfig(settings.LOGGING)
logger = getLogger('mlarchive.custom')

def main():
    parser = argparse.ArgumentParser(description='Scan message and import.')
    parser.add_argument('path')
    parser.add_argument('--limit',type=int,default=0,
                        help='limit processing to N number of messages')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    parser.add_argument('-c','--check',help="check only, dont't import",action='store_true')
    args = parser.parse_args()
    files = os.listdir(args.path)
    listname = os.path.basename(args.path)

    # filter already processed files
    files = filter(lambda x: not x.startswith('_'),files)

    # apply limit if given
    if args.limit > 0:
        files = files[:args.limit]

    for file in files:
        is_spam = False
        fullpath = os.path.join(args.path,file)

        with open(fullpath) as fp:
            try:
                # scan
                subprocess.check_call(['spamc','-c'],stdin=fp)
                if args.verbose:
                    print '%s: clean' % file
            except subprocess.CalledProcessError:
                logger.warning('%s: found spam (%s)' % (progname,fullpath))
                if args.verbose:
                    print "%s: spam" % file
                is_spam = True

            if not is_spam:
                # import message
                try:
                    fp.seek(0)
                    msg = email.message_from_file(fp)
                    mw = _classes.MessageWrapper(msg,listname)
                    if not args.check:
                        mw.save()
                except Exception as error:
                    logger.error('%s: import failed %s (%s)' % (progname, fullpath, error.args))
                    continue

                # mark for later review
                archmsg = mw.archive_message
                archmsg.spam_score = settings.MARK_LOAD_SPAM
                if not args.check:
                    archmsg.save()

                # remove from spam directory
                if not args.check:
                    os.remove(fullpath)

                logger.info('%s: successful import (pk=%s)' % (progname, archmsg.pk))
            else:
                shutil.move(fullpath,os.path.join(args.path,'_' + file))

if __name__ == "__main__":
    main()