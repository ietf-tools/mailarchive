#!/usr/bin/python
'''
Call get_body on each message object.  Use logging in generator
_handler methods to gather stats.

'''
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings'
# -------------------------------------------------------------------------------------

from mlarchive.archive.models import *
import argparse
import glob
import mailbox
import re
import sys

def bodies():
    'Call get_body_html() for every message in db'
    query = Message.objects.filter(pk__lte=10000)
    total = query.count()
    for msg in query:
        try:
            x = msg.get_body_html()
        except UnicodeDecodeError as e:
            print '{0} [{1}]'.format(e, msg.pk)
        if msg.pk % 1000 == 0:
            print 'processed {0} of {1}'.format(msg.pk,total)

def main():
    parser = argparse.ArgumentParser(description='Run an archive scan.')
    parser.add_argument('function')
    args = parser.parse_args()
    func = getattr(sys.modules[__name__], args['function'])
    print func

if __name__ == "__main__":
    main()
