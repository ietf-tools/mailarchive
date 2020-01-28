#!../../../env/bin/python
'''
Given a maildir archive directory and listname this script
will check for each message in the archive db.

Example
./check_maildir.py /a/mailarch/data/archive/dnsop -l dnsop
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import email
import glob

import os
import mailbox
import sys

from django.conf import settings
from mlarchive.archive.models import Message, EmailList

def check_archive(msg,elist):
    msgid = msg['message-id']
    if not msgid:
        return

    msgid = msgid.strip('<>')
    try:
        Message.objects.get(email_list=elist,msgid=msgid)
        print("Found: {}".format(msgid))
    except:
        print("Missing: {} {} {}".format(msg['date'][:17],msg['subject'][:10],msgid))

def main():
    parser = argparse.ArgumentParser(description='Check maildir contents in archive')
    parser.add_argument('path')
    parser.add_argument('-l', '--list', help='the list to process')
    parser.add_argument('-f','--fix',help="perform fix",action='store_true')
    args = vars(parser.parse_args())
    files = glob.glob(os.path.join(args['path'], '*'))
    elist = EmailList.objects.get(name=args['list'])
    for file in files:
        with open(file) as f:
            msg = email.message_from_file(f)
        check_archive(msg,elist)


if __name__ == '__main__':
    main()
