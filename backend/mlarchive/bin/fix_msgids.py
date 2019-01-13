#!/usr/bin/python
"""
Script to scan through archive and identify messages that have archive generated
msgid, then add that id to the message file on disk.
"""
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

from django.conf import settings
from mlarchive.archive.management.commands import _classes
from mlarchive.archive.models import Message

import argparse
import email
import datetime
import logging
import os
import re
import socket
import shutil


import logging
#import logging.config
logging.config.dictConfig(settings.LOGGING)
logger = logging.getLogger('mlarchive.custom')

BACKUP_DIR = '/a/mailarch/data/backup/'

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
        
def main():
    parser = argparse.ArgumentParser(description='Fix unsuppoted date headers.')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    parser.add_argument('-c','--check',help="check only",action='store_true')
    args = parser.parse_args()

    updated = 0
    fqdn = socket.getfqdn()
    messages = Message.objects.filter(msgid__endswith='.ARCHIVE@%s>' % fqdn)
    
    for message in messages:
        file = message.get_file_path()
        with open(file) as fp:
            msg = email.message_from_file(fp)
        orig_msgid = msg['message-id']
            
        if orig_msgid == message.msgid:
            continue
        
        if orig_msgid and orig_msgid != '<>' and orig_msgid != message.msgid:
            print "WARNING Mismatch: db:{}  file:{} [{}]".format(message.msgid,orig_msgid,file)
        elif not args.check:
            updated = updated + 1
            if args.verbose:
                print "replacing {} with {}".format(orig_msgid,message.msgid)

            # adjust headers
            msg.add_header('X-Message-ID',orig_msgid)
            if 'message-id' in msg:
                msg.replace_header('Message-ID',message.msgid)
            else:
                msg.add_header('Message-ID',message.msgid)
    
            # save original file
            list_dir = os.path.basename(os.path.dirname(file))
            backup_dir = os.path.join(BACKUP_DIR,list_dir)
            ensure_dir(backup_dir)
            target = os.path.join(backup_dir,os.path.basename(file))
            if os.path.exists(target):
                os.remove(target)
            shutil.move(file,backup_dir)
        
            # write new file
            # convert line endings to crlf
            output = re.sub("\r(?!\n)|(?<!\r)\n", "\r\n", _classes.flatten_message(msg))
            with open(file,'w') as out:
                out.write(output)
            os.chmod(file,0660)
    
    # print stats
    print "Total messages: {}".format(messages.count())
    print "Messages updated {}".format(updated)

if __name__ == "__main__":
    main()
