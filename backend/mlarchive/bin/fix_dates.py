#!/usr/bin/python
"""
Script to scan through a maildir directory find messages with unsupported date
header, see regex, and replace with proper format.  Original date header is saved
as X-Date, and original file is saved in a backup directory.
"""
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

from django.conf import settings
from mlarchive.archive.management.commands import _classes

import argparse
import email
import datetime
import logging
import os
import pytz
import re
import shutil
import subprocess
import sys
from dateutil.parser import parse

progname = sys.argv[0]

import logging
#import logging.config
logging.config.dictConfig(settings.LOGGING)
logger = logging.getLogger('mlarchive.custom')

# SAMPLE BAD DATE: Mon Aug 21 20:45:35 2006
DATE_PATTERN = re.compile(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+([a-zA-Z]{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})')
BACKUP_DIR = '/a/mailarch/data/backup/'

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        
def convert_date(msg):
    '''Convert unsupported date string to standard email date string'''
    mw = _classes.MessageWrapper(msg,'mylist')
    
    try:
        date = mw.date      # returns a naive UTC date
    except _classes.DateError:
        # handles _very_ specific failure case
        date = parse(msg['sent'])
    return date.strftime('%a, %d %b %Y %H:%M:%S +0000')
    
def main():
    parser = argparse.ArgumentParser(description='Fix unsuppoted date headers.')
    parser.add_argument('path')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    parser.add_argument('-c','--check',help="check only",action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        parser.error('{} must be a directory'.format(args.path))

    fullnames = [ os.path.join(args.path,n) for n in os.listdir(args.path) ]
    files = filter(os.path.isfile,fullnames)

    total = 0
    tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
    
    for file in files:
        with open(file) as fp:
            msg = email.message_from_file(fp)
        
        # determine datefield
        if msg['date']:
            dfield = 'date'
        elif msg['sent']:
            dfield = 'sent'
        else:
            print "No date: {}".format(file)
            continue
            
        # check for future date
        try:
            is_future = parse(msg[dfield],ignoretz=True) > tomorrow
        except Exception as error:
            print "Parse failed {} ({},{})".format(error,msg[dfield],file)
            continue
            
        if DATE_PATTERN.match(msg[dfield]) or dfield == 'sent' or is_future:
            total +=1
            
            try:
                new = convert_date(msg)
            except:
                print "DateError: {} : {}".format(os.path.basename(file),msg[dfield])
                continue
                
            if not new:
                print "DateError: {} : {}".format(os.path.basename(file),msg[dfield])
                continue
                
            if args.check or args.verbose:
                print "{}: {} -> {}".format(os.path.basename(file),msg[dfield],new)
            
            if not args.check:
                # adjust headers
                msg.add_header('X-{}'.format(dfield.capitalize()),msg[dfield])
                if 'date' in msg:
                    msg.replace_header('date',new)
                else:
                    msg.add_header('Date',new)
                    del msg['sent']
            
                # save original file
                list_dir = os.path.basename(os.path.dirname(file))
                backup_dir = os.path.join(BACKUP_DIR,list_dir)
                ensure_dir(backup_dir)
                shutil.move(file,backup_dir)
                
                # write new file
                output = _classes.flatten_message(msg)
                with open(file,'w') as out:
                    out.write(output)
                os.chmod(file,0660)
                
    # print stats
    print "Modified messages: {}".format(total)

if __name__ == "__main__":
    main()
