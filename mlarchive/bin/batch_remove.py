#!/usr/bin/python
'''
Bulk removal of messages from the archive / index.  Takes one argument, the 
integer to use for identifying spam_score of messages to delete.  This script
queues index updates so it can be run in normal production environment.  It will
retrieve all messages with given spam_score and queue for removal in 200 message
chunks.  200 because the default celery task timeout is 300 seconds, and if the
task takes longer it gets terminated, causing all message deletes to be run one-by-one.
With a count of 200 we shouldn't exceed the timeout and even if we do the time
to delete 200 messages individually is not excessive.  Between chunks we poll the
rabbit queue every 30 seconds, if the queue is 0 proceed with the next chunk.  As such
this is a long running script and so should be called from cron if necessary.

References:
https://trac.xapian.org/wiki/FAQ/UniqueIds
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------

import argparse
import base64
import json
import os
import time
import urllib2
import xapian

from django.conf import settings
from celery_haystack.tasks import CeleryXapianBatchRemove
from mlarchive.archive.models import Message

import logging
logpath = os.path.join(settings.DATA_ROOT,'log/batch_remove.log')
logging.basicConfig(filename=logpath,level=logging.DEBUG)


def get_queue():
    """Get the celery queue from local rabbitmq server.  Returns an integer, queue
    length, or None if there is a problem"""
    username = 'guest'
    password = 'guest'
    url = 'http://127.0.0.1:15672/api/queues'
    req = urllib2.Request(url)
    base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
    authheader =  "Basic %s" % base64string
    req.add_header("Authorization", authheader)
    try:
        handle = urllib2.urlopen(req)
    except URLError:
        return None
    data = json.load(handle)
    for q in data:
        if q['name'] == 'celery':
            return q['messages']
    return None
    
def chunks(l, n):
    """Yield successive n-sized chunks from l"""
    for i in xrange(0, len(l), n):
        yield l[i:i+n]


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Batch remove messages')
    parser.add_argument('score')
    args = parser.parse_args()
    
    messages = Message.objects.filter(spam_score=args.score)
    
    for chunk in chunks(messages,200):
        CeleryXapianBatchRemove.delay(chunk)
        while True:
            time.sleep(30)
            q = get_queue()
            if q is None:
                # can't get queue length, wait 8 minutes and proceed
                time.sleep(8*60)
                break
            elif q == 0:
                break


if __name__ == "__main__":
    main()