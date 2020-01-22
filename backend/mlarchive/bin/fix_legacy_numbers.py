#!../../../env/bin/python


'''
This script scans the MHonArc web archive, and creates a record in Legacy for each message

Example:

fix_legacy_numbers.py  --check

Encoding.  MHonArc HTML email pages can be of various encodings, utf8, gbk, windows-1252.
For the purposes of this script we open the mail file in binary mode, using bytes
line.startswith(b'<!--X-Message-Id:'), then decoding the found line using ASCII.
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import glob
import io
import os
import re
import sys
from html.parser import HTMLParser

from mlarchive.archive.models import Legacy, Message


NOIDPATTERN = re.compile(r'.*@NO-ID-FOUND.mhonarc.org')
PATTERN = re.compile(r'<!--X-Message-Id:\s+(.*)\s+-->')
PARSER = HTMLParser()
MESSAGE_COUNT = 0
NOID = 0
MATCH_COUNT = 0
CREATED_COUNT = 0


def process_dirs(dirs, args):
    for name in sorted(dirs):
        path = os.path.join('/a/www/ietf-mail-archive/web', name, 'current')
        files = glob.glob(os.path.join(path, 'msg?????.html' ))
        if not files:
            print("Skipping %s" % name)
            continue
        else:
            print("Fixing %s" % name)

        # clear corrupted data
        Legacy.objects.filter(email_list_id=name).delete()
        Message.objects.filter(email_list__name=name).update(legacy_number=None)
        process_files(name, files, args)


def process_files(listname, files, args):
    for file in files:
        global MESSAGE_COUNT
        MESSAGE_COUNT += 1
        if args.verbose:
            print('File: %s' % file)
        with io.open(file, 'rb') as fp:
            msgid = get_msgid(fp)
            number = int(os.path.basename(file)[3:8])
            process_message(listname, msgid, number, args)


def process_message(listname, msgid, number, args):
    global MATCH_COUNT, CREATED_COUNT
    if args.verbose:
        print("listname={},msgid={},number={}".format(listname, msgid, number))
    
    CREATED_COUNT = CREATED_COUNT + 1
    Legacy.objects.create(msgid=msgid, email_list_id=listname, number=number)
    
    try:
        message = Message.objects.get(email_list__name=listname,msgid=msgid)
        message.legacy_number = number
        message.save()
    except Message.DoesNotExist:
        # print "Warning: msgid not found: {}".format(legacy.msgid)
        pass
    except Message.MultipleObjectsReturned:
        print("Warning: MultipleObjectsReturned {}:{}".format(listname, msgid))


def get_msgid(fp):
    '''Returns msgid from MHonArc HTML message file'''
    global NOID
    for line in fp:
        if line.startswith(b'<!--X-Message-Id:'):
            line = line.decode('ascii')
            match = PATTERN.match(line)
            if match:
                msgid = match.groups()[0]
                # in msgNNNNN.html message-id's are escaped, need to unescape
                msgid = PARSER.unescape(msgid)
                if re.match(NOIDPATTERN, msgid):
                    NOID += 1
            else:
                raise Exception('pattern failed (%s)' % line)
            break
    # _ = str(msgid)  # test for unknown encodings
    return msgid


def main():
    aparser = argparse.ArgumentParser(description='Fix legacy MHonArc message numbers')
    aparser.add_argument('-v', '--verbose', help='verbose output', action='store_true')
    args = aparser.parse_args()

    # scan intersection of public and private lists
    public = os.listdir('/a/www/ietf-mail-archive/web/')
    private = os.listdir('/a/www/ietf-mail-archive/web-secure/')
    dirs = set(public) & set(private)
    process_dirs(dirs, args)

    print("message_count: %d" % MESSAGE_COUNT)
    print("match_count: %d" % MATCH_COUNT)
    print("created_count: %d" % CREATED_COUNT)
    print("NO IDs: %d" % NOID)


if __name__ == "__main__":
    main()
