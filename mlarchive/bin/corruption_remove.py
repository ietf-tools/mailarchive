#!/usr/bin/python
'''
This script reviews messages marked with spam_score bit 16 and removes messages from the
archive that exhibit signs of corruption
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------
from builtins import input

import email
import logging
import os
import sys
import re
from mlarchive.archive.models import Message

import logging
logger = logging.getLogger('mlarchive.custom')

EMBEDDED_FROM_PATTERN = re.compile(r'.+(From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+)')

def exhibits_corruption(message):
    # no subject
    if not message.subject or not message.frm or not message.to:
        print "missing subject, from or to"
        return True
        
    # "Received:" in message body
    for line in message.get_body().splitlines():
        if line.startswith('Received: from '):
            print "received in body"
            return True
    
    fp = open(message.get_file_path())
    emsg = email.message_from_file(fp)
    fp.close()
    
    # headers corrupted
    if not emsg['message-id'] or not emsg['message-id'].endswith('>'):
        print "corrupt header: message-id"
        return True
    if emsg['list-subscribe'] and not emsg['list-subscribe'].endswith(('>',',')):
        print "corrupt header: list-subscribe"
        return True
    if emsg['list-unsubscribe'] and not emsg['list-unsubscribe'].endswith(('>',',')):
        print "corrupt header: list-unsubscribe"
        return True
    
    # any header field contains embedded from line
    for k,v in emsg.items():
        if EMBEDDED_FROM_PATTERN.match(v):
            print "corrupt header: embedded from"
            return True
    
    return False
    
def main():
    corrupted = 0
    messages = []
    for m in Message.objects.exclude(spam_score=0):
        if m.spam_score & 0b00010000:
            messages.append(m)
            
    # ensure all files exist before deleting any
    assert len(messages) == len(set(messages))
    for message in messages:
        assert os.path.exists(message.get_file_path())
    
    for message in messages:
        if not os.path.exists(message.get_file_path()):
            print "Missing message: %s:%s" % (message.email_list,message.hashcode)
        if exhibits_corruption(message):
            logger.info('Script %s removed message [list=%s,hash=%s,msgid=%s,pk=%s]' %
                (sys.argv[0],message.email_list,message.hashcode,message.msgid,
                message.pk))
            corrupted = corrupted + 1
            print "thread message count: {}".format(message.thread.message_set.count())
            message.delete()
            _ = input('Deleted: {}:{}:{}'.format(message.email_list.name,message.msgid,message.get_file_path()))
        else:
            # leave messages marked for time being
            pass
            
    print "Reviewed: {}".format(len(messages))
    print "Total Corrupted: {}".format(corrupted)
    
if __name__ == "__main__":
    main()