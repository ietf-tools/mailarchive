#!/usr/bin/python
'''
Generic scan script.  Define a scan as a function.  Specifiy the function as the
first command line argument.

usage:

scan_all [func name]

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
from mlarchive.bin.scan_utils import *
from mlarchive.archive.management.commands import _classes
from tzparse import tzparse
from pytz import timezone

import argparse
import glob
import mailbox
import re
import sys

date_pattern = re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
dupetz_pattern = re.compile(r'[\-\+]\d{4} \([A-Z]+\)$')

date_formats = ["%a %b %d %H:%M:%S %Y",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%a %b %d %H:%M:%S %Y %Z"]

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def get_date_part(str):
    '''Get the date portion of the envelope header.  Based on the observation
    that all date parts start with abbreviated weekday'''
    match = date_pattern.search(str)
    if match:
        date = match.group()

        # a very few dates have redundant timezone designations on the end
        # which tzparse can't handle.  If this is the case strip it off
        # ie. Wed, 6 Jul 2005 12:24:15 +0100 (BST)
        if dupetz_pattern.search(date):
            date = re.sub(r'\s\([A-Z]+\)$','',date)
        return date
    else:
        return None

def convert_date(date):
    'Try different patterns to convert string to naive UTC datetime object'
    for format in date_formats:
        try:
            result = tzparse(date.rstrip(),format)
            if result:
                # convert to UTC and make naive
                utc_tz = timezone('utc')
                time = utc_tz.normalize(result.astimezone(utc_tz))
                time = time.replace(tzinfo=None)                # make naive
                return time
        except ValueError:
            pass
# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def bodies():
    '''Call get_body_html() for every message in db. Use logging in generator
    _handler methods to gather stats.
    '''
    query = Message.objects.filter(pk__lte=10000)
    total = query.count()
    for msg in query:
        try:
            x = msg.get_body_html()
        except UnicodeDecodeError as e:
            print '{0} [{1}]'.format(e, msg.pk)
        if msg.pk % 1000 == 0:
            print 'processed {0} of {1}'.format(msg.pk,total)

def envelope_date():
    'Quickly test envelope date parsing on every standard mbox file in archive'
    for path in all_mboxs():
    #for path in ['/a/www/ietf-mail-archive/text/lemonade/2002-09.mail']:
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if line.startswith('From '):
                date = get_date_part(line.rstrip())
                if date == None:
                    print path,line
                if not convert_date(date.rstrip()):
                    print path,date

def main():
    parser = argparse.ArgumentParser(description='Run an archive scan.')
    parser.add_argument('function')
    args = vars(parser.parse_args())
    if args['function'] in globals():
        func = globals()[args['function']]
        func()
    else:
        raise argparse.ArgumentTypeError('no scan function: %s' % args['function'])

if __name__ == "__main__":
    main()
