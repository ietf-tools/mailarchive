#!/usr/bin/python
'''
This script will produce a thread ordered view of messages for a given list
comparable to the MHonArc thread view.
'''

# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.production'
django.setup()

# -------------------------------------------------------------------------------------
import argparse
import signal

from mlarchive.archive.models import EmailList, Message


COUNTED = {}
REPLIES = {}
SREPLIES = {}
TLIST_ORDER = []
INDEX2TLOC = {}
HAS_REF_DEPTH = {}
THREAD_LEVEL = {}


def signal_handler(signal, frame):
        global TLIST_ORDER
        print('You pressed Ctrl+C!')
        for line in TLIST_ORDER: 
            print line
        sys.exit(0)


def get_references(message):
    '''Return list of message references, in reverse order'''
    result = [ r.strip('<>') for r in message.references.split() ]
    if len(result) > 1:
        result.reverse()
    return result


def do_thread(message,level):
    global COUNTED, REPLIES, SREPLIES, TLIST_ORDER, INDEX2TLOC, HAS_REF_DEPTH
    repls = []
    srepls = []
    
    print 'do_thread: {}'.format(message.msgid)
    
    # get replies
    if message in REPLIES:
        repls = sorted(REPLIES[message], key = lambda x: (x.date, x.pk))
        #print '{}: {}'.format(message.msgid,repls)
    if message in SREPLIES:
        srepls = sorted(SREPLIES[message], key = lambda x: (x.date, x.pk))
        #print '{}: {}'.format(message.msgid,srepls)
        
    # add index to printed order
    TLIST_ORDER.append(message)
    INDEX2TLOC[message] = len(TLIST_ORDER) - 1
    
    # mark messages
    COUNTED[message] = 1
    THREAD_LEVEL[message] = level
    
    if repls:
        for r in repls:
            if r in COUNTED:
                print 'repls loop detected: {}'.format(r.msgid)
                sys.exit()
            do_thread(r, level + 1 + HAS_REF_DEPTH[r])
    if srepls:
        for r in srepls:
            if r in COUNTED:
                print 'srepls loop detected: {}'.format(r.msgid)
                sys.exit()
            do_thread(r, level + 1 + HAS_REF_DEPTH[r])


def main():
    global COUNTED, REPLIES, SREPLIES, HAS_REF_DEPTH
    signal.signal(signal.SIGINT, signal_handler)
    parser = argparse.ArgumentParser(description='Display thread view')
    parser.add_argument('list',nargs="?")
    args = parser.parse_args()
    
    elist = EmailList.objects.get(name=args.list)
    
    print 'List: {}'.format(elist.name)

    first_subject2index = {}
    has_ref = {}
    has_ref_depth = {}

    # sort by date first for subject based threads
    thread_list = Message.objects.filter(email_list=elist).order_by('date')
    print 'Messages: {}'.format(thread_list.count())
    
    # find first occurrances of subjects
    # might replace with Message.objects.filter(base_subject=xx,references='').order_by('date').first()
    print 'Finding first subjects...'
    for message in thread_list:
        if not message.base_subject:
            continue
        if message.base_subject in first_subject2index or message.references:
            continue
        first_subject2index[message.base_subject] = message
    
    # compute thread data
    print 'Compute thread data...'
    for message in thread_list:
        if message.references:
            depth = 0
            for reference_id in get_references(message):
                if Message.objects.filter(msgid=reference_id).exists():
                    try:
                        reference = Message.objects.get(msgid=reference_id,email_list=elist)
                    except Message.MultipleObjectsReturned:
                        print 'Dupe: {}'.format(reference_id)
                        sys.exit()
                    has_ref[message] = reference
                    HAS_REF_DEPTH[message] = depth
                    REPLIES[reference] = REPLIES.get(reference,[]) + [message]
                    break
                else:
                    depth = depth + 1
        else:
            # check for subject based threading
            if message not in  has_ref:
                if message.base_subject in first_subject2index:
                    reference = first_subject2index[message.base_subject]
                    if reference != message:
                        has_ref[message] = reference
                        HAS_REF_DEPTH[message] = 0
                        SREPLIES[reference] = SREPLIES.get(reference,[]) + [message]

    # calculate thread listing order
    for num,message in enumerate(Message.objects.filter(email_list=elist).order_by('-date')):
        if ( message not in COUNTED and message not in has_ref ):
            print '='*40
            print 'Calculated {} of {}'.format(num,thread_list.count())
            print '{}'.format(message.msgid)
            if message in REPLIES:
                print 'REPLIES: {}'.format(REPLIES[message])
            if message in SREPLIES:
                print 'REPLIES: {}'.format(SREPLIES[message])
            do_thread(message, 0)

    for m in TLIST_ORDER:
        print m.subject + ' .. ' + m.frm.encode('ascii','replace') + ' .. ' + m.msgid

if __name__ == "__main__":
    main()