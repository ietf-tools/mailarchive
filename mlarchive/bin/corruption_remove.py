#!/usr/bin/python
'''
This script reviews messages marked with spam_score = 9 and removes messages from the
archive that exhibit signs of corruption
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

import email
import logging
import re
from mlarchive.archive.models import Message

EMBEDDED_FROM_PATTERN = re.compile(r'.+(From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+)')

def exhibits_corruption(message):
    # no subject
    if not message.subject or not message.frm or not message.to:
        return True
        
    # Received: in message body
    for line in message.get_body().splitlines():
        if line.startswith('Received: from '):
            return True
    
    with open(message.get_file_path()) as fp:
        emsg = email.message_from_file(fp)
    
    # headers corrupted
    if not emsg['message-id'].endswith('>'):
        return True
    if not emsg['list-subscribe'].endswith(('>',',')):
        return True
    if not emsg['list-unsubscribe'].endswith(('>',',')):
        return True
    
    # any header field contains embedded from line
    for k,v in emsg.items():
        if EMBEDDED_FROM_PATTERN.match(v):
            return True
    
    return False
    
def main():
    corrupted = 0
    messages = Message.objects.filter(spam_score=9)
    for message in messages:
        if exhibits_corruption(message):
            print 'Removed {}:{}'.format(message.email_list.name,message.msgid)
            corrupted = corrupted + 1
            message.delete()
        else:
            #message.spam_score = 0
            pass
            
    print "Reviewed: {}".format(messages.count())
    print "Total Corrupted: {}".format(corrupted)
if __name__ == "__main__":
    main()