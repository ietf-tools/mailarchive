#!/usr/bin/python
"""
Script to load messages that were excluded from the initial import.  Takes one
positional argument, the path to the "filtered" directory of files to load.  This must
be in the format ".../listname/_filtered".  spamc is used to determine if the message
is spam.

~/.spamassassin/user_prefs can be used to override global rules.  For instance:

score FH_DATE_IS_19XX 0.1   # lower score of two digit date

"""
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
#path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#if not path in sys.path:
#    sys.path.insert(0, path)
#os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.production'
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

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        os.chmod(path,02777)

def main():
    parser = argparse.ArgumentParser(description='Scan message and import.')
    parser.add_argument('path')
    parser.add_argument('--limit',type=int,default=0,
                        help='limit processing to N number of messages')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    parser.add_argument('-c','--check',help="check only, dont't import",action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        parser.error('{} must be a directory'.format(args.path))

    files = os.listdir(args.path)
    listname = os.path.basename(os.path.dirname(args.path))

    # apply limit if given
    if args.limit > 0:
        files = files[:args.limit]

    for file in files:
        fullpath = os.path.join(args.path,file)

        with open(fullpath) as fp:
            try:
                # scan
                subprocess.check_call(['spamc','-c'],stdin=fp)
                if args.verbose:
                    print '%s: clean' % file
            except subprocess.CalledProcessError:
                # the message is spam
                fp.close()
                logger.warning('%s: found spam (%s)' % (progname,fullpath))
                if args.verbose:
                    print "%s: spam" % file
                if not args.check:
                    spam_dir = os.path.join(settings.ARCHIVE_DIR,listname,'_spam')
                    ensure_dir(spam_dir)
                    spam_path = os.path.join(spam_dir,file)
                    shutil.move(fullpath,spam_path)
                continue

            # import message
            try:
                fp.seek(0)
                msg = email.message_from_file(fp)
                mw = _classes.MessageWrapper(msg,listname)
                # mark for later review
                mw.archive_message.spam_score = settings.MARK_LOAD_SPAM
                if not args.check:
                    mw.save()
            except _classes.DuplicateMessage as error:
                # if duplicate message has been saved to _dupes
                logger.warning("Import Warn [{0}, {1}, {2}]".format(file,error.args,_classes.get_from(mw)))
            except Exception as error:
                logger.error("Import Error [{0}, {1}, {2}]".format(file,error.args,_classes.get_from(mw)))
                _classes.save_failed_msg(msg,listname,error)

            # remove from filtered directory
            if not args.check:
                os.remove(fullpath)

            logger.info('%s: successful import (list=%s,pk=%s)' % (progname, listname, mw.archive_message.pk))


if __name__ == "__main__":
    main()
