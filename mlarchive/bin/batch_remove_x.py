#!/usr/bin/python
'''
Bulk removal of messages from the archive / index.  Takes one argument, the 
integer to use for identifying spam_score of messages to delete.  This script
uses xapian.WritableDatabase so regular database updates must be suspended when
running.

** NOTE ** 
This version bypasses the message index update queue, and therefore cannot
be run in production when queue is in normal operation.

References:
https://trac.xapian.org/wiki/FAQ/UniqueIds
'''

# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.noindex'
django.setup()

# -------------------------------------------------------------------------------------
import argparse
import xapian

from django.conf import settings

from mlarchive.archive.models import Message

import logging
logpath = os.path.join(settings.DATA_ROOT,'log/check_spam.log')
logging.basicConfig(filename=logpath,level=logging.DEBUG)


def remove_messages(messages):
    '''Remove all messages.  First cycle through messages calling
    database.delete_document().  These index actions will be batched by Xapian.  Then
    delete the messages from the db, filesystem
    '''
    print 'Deleting {} messages.'.format(messages.count())
    database = xapian.WritableDatabase(settings.HAYSTACK_XAPIAN_PATH,xapian.DB_OPEN)
    for message in messages:
        idterm = 'Qarchive.message.{pk}'.format(pk=message.pk)
        #plist = database.postlist_begin('Qarchive.message.{pk}'.format(pk=message.pk))
        #docid = plist.get_docid()
        database.delete_document(idterm)
    database.close()
    messages.delete()
    
    
def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Batch remove messages')
    parser.add_argument('score')
    args = parser.parse_args()
    
    messages = Message.objects.filter(spam_score=args.score)
    remove_messages(messages)
    
    
if __name__ == "__main__":
    main()