#!/usr/bin/python
'''
This script is a quick and dirty script to load messages into the archive db

to run first do
export DJANGO_SETTINGS_MODULE=mlarchive.settings
'''

import sys
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast')
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast/mlarchive')

from django.core.management import setup_environ
from django.db.utils import IntegrityError
from mlarchive import settings

setup_environ(settings)

from mlarchive.archive.models import *
from email.utils import parseaddr

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
SOURCE_DIR = '/a/www/ietf-mail-archive/'
#FILE_PATTERN = re.compile(r'^\d{4}-\d{2}.mail$')
# get only recent files (2010 on) the older ones have different format??
FILE_PATTERN = re.compile(r'^201[0-3]-\d{2}.mail$')
IRTS = 0
LOADED = 0
MISSING_IRT = 0
SKIPPED = 0

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
    and return it's thread id, otherwise return a new thread id.  This is crude for many reasons.
    ie. what if the referenced message isn't loaded yet?  We load message files in date order
    to minimize this.
    '''
    global MISSING_IRT
    global IRTS
    irt = msg.get('In-Reply-To','')
    if irt:
        IRTS += 1
        try:
            irt_msg = Message.objects.get(msgid=irt)
            thread = irt_msg.thread
        except (Message.DoesNotExist, Message.MultipleObjectsReturned):
            MISSING_IRT += 1
            thread = Thread.objects.create()
    else:
        thread = Thread.objects.create()
    return thread
    
def import_mbox(group,path,mlist):
    global LOADED
    global SKIPPED
    rgx = re.compile('[<>]')
    
    mb = mailbox.mbox(path)
    for m in mb:
        # get date from "from" line
        line = m.get_from()
        if '@' in line:
            # mhonarc archive
            date_parts = line.split()[1:]
        else:
            # pipermail archive
            date_parts = line.split()[3:]
        
        # this is a Q&D load.  The commands in the try block could result in various errors
        # just catch these and proceed to the next record
        try:
            # convert date
            # TODO: use email.utils.parsedate
            date = datetime.datetime.strptime(' '.join(date_parts),'%a %b %d %H:%M:%S %Y')
            hash = get_hash(mlist.name,m['Message-ID'])
            # strip brackets, causes all parts to be concat together, bad
            #f=handle_header(m['From'])
            #frm=rgx.sub('',f)
            msg = Message(date=date,
                      email_list=mlist,
                      frm = handle_header(m['From']),
                      #frm_email=parseaddr(m['From'])[1],
                      hashcode=hash,
                      #headers = 'this is a test',
                      inrt=m.get('In-Reply-To','').strip('<>'),
                      msgid=m['Message-ID'].strip('<>'),
                      subject=handle_header(m['Subject']),
                      thread=get_thread(m),
                      to=handle_header(m['To']) if m['To'] != None else '')
            msg.save()
            
            # save disk object
            path = os.path.join(settings.ARCHIVE_DIR,mlist.name,hash)
            if not os.path.exists(os.path.dirname(path)):
                os.mkdir(os.path.dirname(path))
            with open(path,'w') as f:
                f.write(m.as_string())
            
            LOADED = LOADED + 1
        except (MySQLdb.Warning,MySQLdb.OperationalError,IntegrityError,ValueError,TypeError):
        #except IOError:   # uncomment for testing
            # TypeError: if Message-ID is None, abfab
            SKIPPED = SKIPPED + 1
    
def load(lists,private=False):
    subdir = 'text-secure' if private else 'text'
    for dir in lists:
        print 'Loading: %s' % dir
        # create list object
        mlist,created = EmailList.objects.get_or_create(name=dir,description=dir,private=private)
        
        mboxs = [ f for f in os.listdir(os.path.join(SOURCE_DIR,subdir,dir)) if FILE_PATTERN.match(f) ]
        
        # we need to import the files in chronological order so thread resolution works
        sorted_mboxs = sorted(mboxs)
        
        for filename in sorted_mboxs:
            path = os.path.join(SOURCE_DIR,subdir,dir,filename)
            import_mbox(dir,path,mlist)
            
# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main(): 
    # which email lists to load
    all = os.listdir(os.path.join(SOURCE_DIR,'text'))
    #public_lists = ('ccamp','alto')
    public_lists = ('abfab','alto','ancp','autoconf','bliss','ccamp','cga-ext','codec','dane','dmm','dnsop','dime','discuss','emu','gen-art','grow','hipsec','homenet','i2rs','ipsec','netconf','sip','simple')
    #public_lists = [ d for d in all if d.startswith(('a','b','c')) ]
    #public_lists = all
    
    #secure_lists = ('ietf82-team','ietf83-team','ietf84-team','media','rsoc')
    secure_lists = ('ietf82-team','ietf83-team','ietf84-team')
    
    load(public_lists)
    load(secure_lists,private=True)
    
    print "LOADED: %d, SKIPPED: %s, IRTS %s, MISSING IRTs %s" % (LOADED,SKIPPED,IRTS,MISSING_IRT)
    
if __name__ == "__main__":
    main()
