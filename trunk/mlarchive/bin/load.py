#!/usr/bin/python
'''
This script is a quick and dirty script to load messages into the archive db

to run first do
export DJANGO_SETTINGS_MODULE=mlarchive.settings
'''

import sys
sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast')
sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast/mlarchive')

from django.core.management import setup_environ
from django.db.utils import IntegrityError
from mlarchive import settings

setup_environ(settings)

from mlarchive.archive.models import *

import datetime
import re
import os
import mailbox
import MySQLdb
import hashlib
import base64

# --------------------------------------------------
# Globals
# --------------------------------------------------
LOADED = 0
SKIPPED = 0
MISSING_IRT = 0
IRTS = 0

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def get_hash(list_post,msgid):
    '''
    Takes the name of the email list and msgid and returns the hashcode
    '''
    sha = hashlib.sha1(msgid)
    sha.update(list_post)
    return base64.urlsafe_b64encode(sha.digest())
    
def get_thread(msg):
    '''
    This is a very basic thread algorithm.  If 'In-Reply-To-' is set, look up that message 
    and return it's thread id, otherwise return a new thread id.
    '''
    global MISSING_IRT
    global IRTS
    irt = msg.get('In-Reply-To','').strip('<>')
    if irt:
        IRTS += 1
        try:
            irt_msg = Message.objects.get(msgid=irt)
            thread = irt_msg.thread
        except (Message.DoesNotExist, Message.MultipleObjectsReturned):
            MISSING_IRT += 1
            thread = Thread.objects.create()
            #print irt
    else:
        thread = Thread.objects.create()
    return thread
    
def import_mbox(group,path,mlist):
    global LOADED
    global SKIPPED
    mb = mailbox.mbox(path)
    for m in mb:
        # get date from "from" line
        line = m.get_from()
        parts = line.split()[3:]
        # this is a Q&D load.  The commands in the try block could result in various errors
        # just catch these and proceed to the next record
        try:
            # convert date
            date = datetime.datetime.strptime(' '.join(parts),'%a %b %d %H:%M:%S %Y')
            hash = get_hash(mlist.name,m['Message-ID'])
            msg = Message(frm=m['From'],
                      date=date,
                      subject=m['Subject'],
                      hashcode=hash,
                      inrt=m.get('In-Reply-To',''),
                      msgid=m['Message-ID'].strip('<>'),
                      email_list=mlist,
                      thread=get_thread(m),
                      headers = 'this is a test',
                      body=m.get_payload())
            msg.save()
            
            # save disk object
            path = os.path.join(settings.ARCHIVE_DIR,mlist.name,hash)
            if not os.path.exists(os.path.dirname(path)):
                os.mkdir(os.path.dirname(path))
            with open(path,'w') as f:
                f.write(m.as_string())
            
            LOADED = LOADED + 1
        except (MySQLdb.Warning,MySQLdb.OperationalError,IntegrityError, ValueError):
            SKIPPED = SKIPPED + 1
    
# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    # the pipermail public mail directory with mbox files
    root = '/a/mailman/archives/public'
    all = os.listdir(root)
    #dirs = ('16ng','ccamp')
    #dirs = ('abfab','alto','ancp','autoconf','ccamp','dime','discuss','ipsec','netconf','sip','simple')
    dirs = [ d for d in all if d.startswith(('a','b','c')) ]
    #dirs = all
    r1 = re.compile(r'^\d{4}-.*.txt$')
    
    # load all list names
    for name in all:
        EmailList.objects.create(name=name,description=name)
        
    for dir in dirs:
        print 'Loading: %s' % dir
        # create list object
        mlist,created = EmailList.objects.get_or_create(name=dir,description=dir)
        
        mboxs = [ f for f in os.listdir(os.path.join(root,dir)) if r1.match(f) ]
        # we need to import the files in chronological order so thread resolution works
        sorted_mboxs = sorted(mboxs, key=lambda a: datetime.datetime.strptime(a.split('.')[0], '%Y-%B'))
        for filename in sorted_mboxs:
            path = os.path.join(root,dir,filename)
            import_mbox(dir,path,mlist)
                
    print "LOADED: %d, SKIPPED: %s, IRTS %s, MISSING IRTs %s" % (LOADED,SKIPPED,IRTS,MISSING_IRT)
    
if __name__ == "__main__":
    main()
