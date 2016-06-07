#!/usr/bin/python
'''
This script will scan messages in the archive, identify spam and remove it (move it
to the _spam directory)
'''

# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.development'
django.setup()

# -------------------------------------------------------------------------------------
import argparse
import email

from celery_haystack.utils import get_update_task
from django.conf import settings

from mlarchive.archive.forms import get_list_info
from mlarchive.archive.inspectors import *
from mlarchive.archive.management.commands._classes import MessageWrapper
from mlarchive.archive.models import *

import logging
logpath = os.path.join(settings.DATA_ROOT,'log/check_spam.log')
logging.basicConfig(filename=logpath,level=logging.DEBUG)


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Check archive for spam')
    parser.add_argument('-i', '--inspector', help="enter the inspector class to use")
    parser.add_argument('-l', '--list', help="enter the email list name to check")
    parser.add_argument('-r','--remove',help="remove spam.  default is check only",action='store_true')
    args = parser.parse_args()
    stat = {}
    
    if not EmailList.objects.filter(name=args.list).exists():
        parser.error('List {} does not exist'.format(args.list))
    
    inspector_class = eval(args.inspector)
    
    stat['scanned'] = Message.objects.filter(email_list__name=args.list).count()
    stat['spam'] = 0
    
    for message in Message.objects.filter(email_list__name=args.list):
        path = message.get_file_path()
        with open(path) as f:
            msg = email.message_from_file(f)
        mw = MessageWrapper(msg,args.list)
        inspector = inspector_class(mw,{'check_only':not args.remove})
        try:
            inspector.inspect()
        except SpamMessage:
            stat['spam'] = stat['spam'] + 1
            if args.remove:
                message.delete()

    for k,v in stat.items():
        print "{}:{}".format(k,v)
    
if __name__ == "__main__":
    main()