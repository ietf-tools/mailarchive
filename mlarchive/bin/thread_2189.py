#!/usr/bin/python
'''
Related to Ticket #2189
https://trac.tools.ietf.org/tools/ietfdb/ticket/2189

Locate messages that should have been matched to an existing thread from the
subject line but weren't

'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import datetime
import re

from mlarchive.archive.models import Message, Thread
from mlarchive.archive.management.commands._classes import subject_is_reply

MSGID_PATTERN = re.compile(r'<([^>]+)>')
date = datetime.datetime(2016,11,1)
query = Message.objects.filter(date__gte=date,email_list__name='sipcore')
#threads = Thread.objects.filter(date__gte=date,first__email_list__name='sipcore')
threads = Thread.objects.filter(date__gte=date).order_by('date')

def get_thread(msg):
    # try References
    if msg.references:
        msgids = re.findall(MSGID_PATTERN,msg.references)
        for msgid in msgids:
            try:
                message = Message.objects.get(email_list=msg.email_list,msgid=msgid)
                return message.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                pass

    # try In-Reply-to.  Use first msgid found, typically only one
    if msg.in_reply_to_value:
        msgids = re.findall(MSGID_PATTERN,msg.in_reply_to_value)
        if msgids:
            try:
                message = Message.objects.get(email_list=msg.email_list,msgid=msgids[0])
                return message.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                pass

    # check subject
    if msg.subject != msg.base_subject:
        messages = Message.objects.filter(email_list=msg.email_list,
                                          date__lt=msg.date,
                                          subject=msg.base_subject).order_by('-date')
        if messages:
            return messages[0].thread

def get_ascii(value):
    '''Returns ascii of value'''
    return value.encode('ascii',errors='replace')

def main():
    parser = argparse.ArgumentParser(description="Scan for broken threads")
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose mode')
    args = parser.parse_args()
    total = 0
    monthly_total = 0
    previous_date = date
    for thread in threads:
        if thread.date.month != previous_date.month:
            print '{}:{}'.format(previous_date.strftime("%Y-%m"),monthly_total)
            previous_date = thread.date
            monthly_total = 0
        msg = thread.first
        if subject_is_reply(msg.subject):
            messages = Message.objects.filter(email_list=msg.email_list,
                                              date__lt=msg.date,
                                              base_subject=msg.base_subject).order_by('-date')
            if messages:
                total = total + 1
                monthly_total = monthly_total + 1
                if args.verbose:
                    print "Found {},{},{} should be {}".format(
                        msg.pk,
                        get_ascii(msg.subject),
                        msg.date,
                        messages.first().thread.pk)

    print 'Total: {}'.format(total)

if __name__ == "__main__":
    main()