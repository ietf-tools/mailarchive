#!/usr/bin/python
'''
This is a utility script that handles loading multiple archives

to run first do
export DJANGO_SETTINGS_MODULE=mlarchive.settings
'''
import sys
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast')
#sys.path.insert(0, '/a/home/rcross/src/amsl/mlabast/mlarchive')

from django.core.management import setup_environ
from django.core.management.base import CommandError
from django.db.utils import IntegrityError
from mlarchive import settings

setup_environ(settings)

from django.core.management import call_command
from mlarchive.archive.management.commands._classes import ListError
import glob
import re
import os

# --------------------------------------------------
# Globals
# --------------------------------------------------
SOURCE_DIR = '/a/www/ietf-mail-archive/'
#FILE_PATTERN = re.compile(r'^\d{4}-\d{2}.mail$')
# get only recent files (2010 on) the older ones have different format??
# FILE_PATTERN = re.compile(r'^201[0-3]-\d{2}(|.mail)$')
FILE_PATTERN = re.compile(r'^\d{4}-\d{2}(|.mail)$')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def get_format(filename):
    '''
    Function to determine the type of mailbox file whose filename is provided.
    mmdf: starts with 4 control-A's
    mbox: starts with "From "
    '''
    with open(filename) as f:
        line = f.readline()
        if line == '\x01\x01\x01\x01\n':
            return 'mmdf'
        elif line.startswith('From '):
            return 'mbox'

def load(lists,private=False):
    subdir = 'text-secure' if private else 'text'
    for dir in lists:
        print 'Loading: %s' % dir
        # create list object
        # mlist,created = EmailList.objects.get_or_create(name=dir,description=dir,private=private)
        
        mboxs = [ f for f in os.listdir(os.path.join(SOURCE_DIR,subdir,dir)) if FILE_PATTERN.match(f) ]
        
        # we need to import the files in chronological order so thread resolution works
        sorted_mboxs = sorted(mboxs)
        
        for filename in sorted_mboxs:
            path = os.path.join(SOURCE_DIR,subdir,dir,filename)
            format = get_format(path)
            # TODO if not empty
            try:
                call_command('load', path, test=True, format=format, listname=dir)
            except ListError:
                print 'ListError'

# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main(): 
    # which email lists to load
    all = os.listdir(os.path.join(SOURCE_DIR,'text'))
    #public_lists = ('ccamp','alto')
    public_lists = ('ietf',)
    #public_lists = ('abfab','alto','ancp','autoconf','bliss','ccamp','cga-ext','codec','dane','dmm','dnsop','dime','discuss','emu','gen-art','grow','hipsec','homenet','i2rs','ipsec','netconf','sip','simple')
    #public_lists = [ d for d in all if d.startswith(('a','b','c')) ]
    #public_lists = all
    
    #secure_lists = ('ietf82-team','ietf83-team','ietf84-team','media','rsoc')
    secure_lists = ('ietf82-team','ietf83-team','ietf84-team')
    
    load(public_lists)
    #load(secure_lists,private=True)
    
    #print "LOADED: %d, SKIPPED: %s, IRTS %s, MISSING IRTs %s" % (LOADED,SKIPPED,IRTS,MISSING_IRT)
    
if __name__ == "__main__":
    main()