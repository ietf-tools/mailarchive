#!../../../env/bin/python
'''
This script will scan messages in the archive, identify spam and remove it (move it
to the _spam directory)
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import dateutil.parser
import email
import os

from celery_haystack.utils import get_update_task
from django.conf import settings

from mlarchive.archive.inspectors import *
from mlarchive.archive.mail import MessageWrapper
from mlarchive.archive.models import *

import logging
logpath = os.path.join(settings.DATA_ROOT,'log/check_spam.log')
logging.basicConfig(filename=logpath,level=logging.DEBUG)


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Check archive for spam')
    parser.add_argument('-i', '--inspector', help="enter the inspector class to use", required=True)
    parser.add_argument('-l', '--list', help="enter the email list name to check")
    parser.add_argument('-m', '--mark', type=int, help="enter integer to mark message with (field=spam_score)")
    parser.add_argument('-r', '--remove', help="remove spam.  default is check only",action='store_true')
    parser.add_argument('-s', '--start', help="enter the date to start check YYYY-MM-DDTHH:MM:SS")
    args = parser.parse_args()
    stat = {}
    
    if args.list and not EmailList.objects.filter(name=args.list).exists():
        parser.error('List {} does not exist'.format(args.list))
    
    inspector_class = eval(args.inspector)
    
    kwargs = {}
    if args.list:
        kwargs['email_list__name'] = args.list
    if args.start:
        kwargs['date__gte'] = dateutil.parser.parse(args.start)
        
    queryset = Message.objects.filter(**kwargs)
    stat['scanned'] = queryset.count()
    stat['spam'] = 0
    
    for message in queryset:
        path = message.get_file_path()
        with open(path) as f:
            msg = email.message_from_file(f)
        mw = MessageWrapper.from_message(msg,args.list)
        inspector = inspector_class(mw,{'check_only':not args.remove})
        try:
            inspector.inspect()
        except SpamMessage:
            stat['spam'] = stat['spam'] + 1
            if args.mark:
                message.spam_score = args.mark
                message.save()
            if args.remove:
                message.delete()

    for k,v in list(stat.items()):
        print("{}:{}".format(k,v))
    
if __name__ == "__main__":
    main()
