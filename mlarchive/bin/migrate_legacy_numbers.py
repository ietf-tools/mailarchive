#!/usr/bin/python
'''
This script iterates over Legacy records for one list or all and populates the 
Message.legacy field to allow redirection of old archive URLs.

Example:

get_legacy_numbers.py testlist

'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(django_settings='mlarchive.settings.noindex')
# -------------------------------------------------------------------------------------

import argparse

from mlarchive.archive.models import Legacy, Message, EmailList


def process(query):
    elist = get_list(query[0])
    last_id = query[0].email_list_id
    for legacy in query:
        if legacy.email_list_id != last_id:
            last_id = legacy.email_list_id
            elist = get_list(legacy)
        if elist is None:
            continue

        try:
            message = Message.objects.get(email_list=elist,msgid=legacy.msgid)
            message.legacy_number = legacy.number
            message.save()
        except Message.DoesNotExist:
            print "Warning: msgid not found: {}".format(legacy.msgid)

def get_list(legacy):
    try:
        elist = EmailList.objects.get(name=legacy.email_list_id)
        return elist
    except EmailList.DoesNotExist:
        print "Warning: list not found: {}".format(legacy.email_list_id)

def main():
    aparser = argparse.ArgumentParser(description='Scan archive for spam.')
    aparser.add_argument('list',nargs="?",default=None)     # positional argument
    aparser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    aparser.add_argument('-c','--check',help="check only, dont't import",action='store_true')
    args = aparser.parse_args()
    
    if args.check:
        print "Check only..."

    if args.list:
        print "List: {}".format(args.list)
        query = Legacy.objects.filter(email_list_id=args.list)

    else:
        query = Legacy.objects.all().order_by('email_list_id')

    process(query)

    print "{} records processed.".format(query.count())

if __name__ == "__main__":
    main()