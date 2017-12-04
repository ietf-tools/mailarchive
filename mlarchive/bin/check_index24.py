#!/usr/bin/python
'''
This script will query all messages new as of yesterday and ensure
that they exist in the archive
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------

import argparse
import datetime
import os
from django.conf import settings
from haystack.query import SearchQuerySet
from mlarchive.archive.models import Message

import logging
logpath = os.path.join(settings.DATA_ROOT,'log/check_index24.log')
logging.basicConfig(filename=logpath,level=logging.DEBUG)


def main():
    parser = argparse.ArgumentParser(description='Check that yesterdays messages are indexed')
    parser.add_argument('-f','--fix',help="perform fix",action='store_true')
    args = parser.parse_args()
    
    today = datetime.datetime.now()
    yesterday =  today - datetime.timedelta(days=1)
    start = yesterday.replace(hour=0,minute=0,second=0,microsecond=0)
    end = today.replace(hour=0,minute=0,second=0,microsecond=0)
    count = 0
    stat = {}
    messages = Message.objects.filter(updated__gte=start,updated__lt=end)
    for message in messages:
        sqs = SearchQuerySet().filter(msgid=message.msgid,email_list__in=[message.email_list.name.replace('-', ' ')])
        if sqs.count() != 1:
            print "Message not indexed.  {list}: {msgid}".format(
                list=message.email_list,
                msgid=message.msgid)
            count = count + 1
            logging.warning(message.msgid + '\n')
            stat[message.email_list.name] = stat.get(message.email_list.name,0) + 1
            if args.fix:
                message.save()
            

    print "Index Check {date}".format(date=start.strftime('%Y-%m-%d'))
    print "Checked {count}".format(count=messages.count())
    print "Missing {count}".format(count=count)
    for k,v in stat.items():
        print "{}:{}".format(k,v)
    
if __name__ == "__main__":
    main()
