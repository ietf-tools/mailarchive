#!/usr/bin/python
'''
This script reviews messages removed by corruption_remove and runs corruption check
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------

import email
import logging
import os
import re
from mlarchive.archive.models import Message
from django.core.management import call_command

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

EMBEDDED_FROM_PATTERN = re.compile(r'.+(From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+)')

def exhibits_corruption(message):
    # no subject
    if not message['subject'] or not message['from'] or not message['to']:
        #print "missing subject, from or to"
        return True
        
    # "Received:" in message body
    lines = []
    for part in message.walk():
        if part.get_content_type() == "text/plain":
            lines.extend(part.get_payload().splitlines())
    for line in lines:
        if line.startswith('Received: from '):
            #print "received in body"
            return True

    # headers corrupted
    if not message['message-id'] or not message['message-id'].endswith('>'):
        #print "corrupt header: message-id"
        return True
    if message['list-subscribe'] and not message['list-subscribe'].endswith(('>',',')):
        #print "corrupt header: list-subscribe"
        return True
    if message['list-unsubscribe'] and not message['list-unsubscribe'].endswith(('>',',')):
        #print "corrupt header: list-unsubscribe"
        return True
    
    # any header field contains embedded from line
    for k,v in message.items():
        if EMBEDDED_FROM_PATTERN.match(v):
            #print "corrupt header: embedded from"
            return True
    
    return False
    
def main():
    uncorrupted = []
    with open('/a/mailarch/data/log/save/find.out') as fp:
        lines = fp.readlines()
    
    for line in lines:
        path = os.path.join('/a/mailarch/data',line[2:].strip())
        with open(path) as fp:
            message = email.message_from_file(fp)
        if not exhibits_corruption(message):
            uncorrupted.append(path)
            print "not corrupt: {}".format(path)
            listname = path.split('/')[-3]
            call_command('load', path, listname=listname)
            _ = raw_input('Return to continue')

    _ = raw_input('Return to continue')
    for p in uncorrupted:
        ndir = os.path.dirname(os.path.dirname(p))
        nbase = os.path.basename(p)
        npath = os.path.join(ndir,nbase)
        if os.path.exists(npath) and os.path.getsize(npath) == os.path.getsize(p):
            os.remove(p)
            
    print "Reviewed: {}".format(len(lines))
    print "Total unCorrupted: {}".format(len(uncorrupted))
    
if __name__ == "__main__":
    main()