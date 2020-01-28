#!../../../env/bin/python
"""
Script to scan through a maildir directory (or entire archive) find messages with
no Date header, and add one.
"""
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import email
import logging
import operator
import os
import shutil
import sys
import time

from django.conf import settings
from mlarchive.archive.models import EmailList, Message
from mlarchive.archive.management.commands import _classes

progname = sys.argv[0]

import logging
#import logging.config
logging.config.dictConfig(settings.LOGGING)
logger = logging.getLogger('mlarchive.custom')

BACKUP_DIR = '/a/mailarch/data/backup/'

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        #os.chmod(path,02777)

def main():
    parser = argparse.ArgumentParser(description='Fix missing date headers.')
    # parser.add_argument('list')
    parser.add_argument('-l', '--list', help="enter the email list name to check")
    parser.add_argument('-c','--check',help="check only",action='store_true')
    args = parser.parse_args()

    if args.list:
        if not EmailList.objects.filter(name=args.list).exists():
            parser.error('List {} does not exist'.format(args.list))
        messages = Message.objects.filter(email_list__name=args.list)
    else:
        messages = Message.objects.all().order_by('email_list__name')

    stat = {}
    scanned = messages.count()
    missing_date = 0
    
    listname = ''
    for message in messages:
        if message.email_list.name != listname:
            print('{}:{}'.format(listname,stat.get(listname,0)))
            listname = message.email_list.name

        path = message.get_file_path()
        with open(path) as fp:
            msg = email.message_from_file(fp)

        if 'Date' in msg:
            continue

        stat[listname] = stat.get(listname,0) + 1
        missing_date = missing_date + 1
        
        if not args.check:
            # get date as RFC 2822 date
            date = message.date
            dtuple = date.timetuple()
            timestamp = time.mktime(dtuple)
            new_date = email.utils.formatdate(timestamp)

            # adjust headers
            msg.add_header('X-Date','(the original message had no date)')
            msg.add_header('Date',new_date)

            # save original file
            list_dir = os.path.basename(os.path.dirname(path))
            backup_dir = os.path.join(BACKUP_DIR,list_dir)
            ensure_dir(backup_dir)
            if not os.path.exists(os.path.join(backup_dir,os.path.basename(path))):
                shutil.move(path,backup_dir)
            
            # write new file
            output = _classes.flatten_message(msg)
            with open(path,'w') as out:
                out.write(output)
            os.chmod(path,0o660)
                
    # print stats
    print()
    for k,v in sorted(list(stat.items()), key=operator.itemgetter(1)):
        print("{}:{}".format(k,v))
        
    print()
    print("Total scanned: {}".format(scanned))
    print("Missing date: {}".format(missing_date))

if __name__ == "__main__":
    main()
