#!../../../env/bin/python
'''
This script iterates over Legacy records for one list or all and populates the 
Message.legacy field to allow redirection of old archive URLs.

Example:

get_legacy_numbers.py testlist

'''
# Standalone broilerplate -------------------------------------------------------------
from .django_setup import do_setup
do_setup(django_settings='mlarchive.settings.noindex')
# -------------------------------------------------------------------------------------

import argparse

from mlarchive.archive.models import Legacy, Message, EmailList


def process(query):
    for legacy in query:
        try:
            message = Message.objects.get(email_list__name=legacy.email_list_id,msgid=legacy.msgid)
            if message.legacy_number != legacy.number:
                message.legacy_number = legacy.number
                message.save()
        except Message.DoesNotExist:
            pass
        except Message.MultipleObjectsReturned:
            print("Warning: MultipleObjectsReturned {}:{}".format(legacy.email_list_id.name, legacy.msgid))

def main():
    aparser = argparse.ArgumentParser(description='Migrate legacy numbers')
    aparser.add_argument('list',nargs="?",default=None)     # positional argument
    aparser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    aparser.add_argument('-c','--check',help="check only, dont't import",action='store_true')
    args = aparser.parse_args()
    
    if args.check:
        print("Check only...")

    if args.list:
        print("List: {}".format(args.list))
        query = Legacy.objects.filter(email_list_id=args.list)

    else:
        query = Legacy.objects.all()

    process(query)

    print("{} records processed.".format(query.count()))

if __name__ == "__main__":
    main()
