#!/usr/bin/python
'''
Quick dump of subject lines, listid_true.txt and listid_false.txt
'''

# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.production'
django.setup()

# -------------------------------------------------------------------------------------
import argparse
import email

from celery_haystack.utils import get_update_task
from django.conf import settings

from mlarchive.archive.forms import get_list_info
from mlarchive.archive.management.commands._classes import MessageWrapper
from mlarchive.archive.models import *

import logging
logpath = os.path.join(settings.DATA_ROOT,'log/check_spam.log')
logging.basicConfig(filename=logpath,level=logging.DEBUG)


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Check archive for spam')
    parser.add_argument('list')
    args = parser.parse_args()
    
    if not EmailList.objects.filter(name=args.list).exists():
        parser.error('List {} does not exist'.format(args.list))
    
    listid_true = open('listid_true.txt', 'w')
    listid_false = open('listid_false.txt', 'w')
    
    for message in Message.objects.filter(email_list__name=args.list):
        path = message.get_file_path()
        with open(path) as f:
            msg = email.message_from_file(f)
        subject = msg.get('Subject','')
        subject = (subject[:40] + '..') if len(subject) > 40 else subject
        if msg.has_key('List-Id'):
            listid_true.write('{0:<48}{1}\n'.format(subject,msg['From']))
        else:
            listid_false.write('{0:<48}{1}\n'.format(subject,msg['From']))
            
            
    listid_false.close()
    listid_true.close()
    
if __name__ == "__main__":
    main()
