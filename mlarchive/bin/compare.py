#!/usr/bin/python
'''
Compare legacy archive with new archive and report descrepencies
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

import argparse
import datetime
import mailbox

from dateutil.parser import *
from mlarchive.bin.scan_utils import all_mboxs
from mlarchive.archive.models import Message
from mlarchive.archive.management.commands import _classes

parser = argparse.ArgumentParser()
parser.add_argument("start", help="enter the date to start comparison YYYY-MM-DDTHH:MM:SS")
parser.add_argument('-l', '--load', action='store_true', help='import missing messages')
args = parser.parse_args()

start_date = parse(args.start)
compstring = start_date.strftime('%Y-%m')
total = 0
missing = 0
imported = 0

for file in all_mboxs():
    basename = os.path.basename(file)
    if basename[:7] >= compstring:
        statinfo = os.stat(file)
        modified = datetime.datetime.fromtimestamp(statinfo.st_ctime)
        if modified > start_date:
            mbox = mailbox.mbox(file)
            for message in mbox:
                try:
                    msgid = message.get('Message-ID').strip('<>')
                except AttributeError as e:
                    continue
                listname = os.path.basename(os.path.dirname(file))
                mw = _classes.MessageWrapper(message, listname)
                msg_date = mw.get_date()
                if msg_date >= start_date:
                    total += 1
                    try:
                        Message.objects.get(msgid=msgid,email_list__name=listname)
                    except Message.DoesNotExist:
                        missing += 1
                        if args.load:
                            status = _classes.archive_message(message.as_string(),
                                                              listname,
                                                              save_failed=False)
                            if status == 0:
                                status_message = 'imported'
                                imported += 1
                            else:
                                status_message = 'import failed'
                        else:
                            status_message = ''
                        print "%s, %s, %s, %s" % (listname,message['subject'][:20],message['date'],status_message)

print "Total: %d\nMissing: %d\nImported: %d" % (total, missing, imported)


