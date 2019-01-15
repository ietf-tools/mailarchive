#!/usr/bin/python
from __future__ import absolute_import, division, print_function, unicode_literals

'''
This script scans the MHonArc web archive, and creates a record in Legacy for each message
Based on pre-import.py, with changes for partial runs.  The Leagcy table will also be used
for redirecting requests to the old archive to the new one.

Example:

get_legacy_numbers.py testlist  --check

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

from mlarchive.archive.models import Legacy


NOIDPATTERN = re.compile(r'.*@NO-ID-FOUND.mhonarc.org')
PATTERN = re.compile(r'<!--X-Message-Id:\s+(.*)\s+-->')
PARSER = HTMLParser()
MESSAGE_COUNT = 0
NOID = 0
MATCH_COUNT = 0
CREATED_COUNT = 0


def process_dirs(dirs, args):
    for dir in sorted(dirs):
        listname = dir.split('/')[-3]
        print("Importing %s" % listname)
        files = glob.glob(dir + 'msg?????.html')
        process_files(listname, files, args)


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

    try:
        obj = Legacy.objects.get(msgid=msgid, email_list_id=listname)
        MATCH_COUNT += 1
        if obj.number != number:
            print('mismatch: object:{}\t{} != {}'.format(obj.id, obj.number, number))
        elif args.verbose:
            print("found match {}:{}:{}".format(listname, msgid, number))
    except Legacy.DoesNotExist:
        CREATED_COUNT += 1
        if not args.check:
            # print 'creating record'
            Legacy.objects.create(msgid=msgid, email_list_id=listname, number=number)
        else:
            if args.verbose:
                print("would have created record {}:{}->{}".format(listname, msgid, number))


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
    aparser = argparse.ArgumentParser(description='Get legacy MHonArc message numbers')
    aparser.add_argument('list', nargs="?", default='*')     # positional argument
    aparser.add_argument('-v', '--verbose', help='verbose output', action='store_true')
    aparser.add_argument('-c', '--check', help="check only, dont't import", action='store_true')
    aparser.add_argument('--file', type=str)
    args = aparser.parse_args()

    if args.check:
        print("Check only...")

    if args.file:
        # import one file only
        print("Processing File {}".format(args.file))
        listname = args.file.split('/')[-3]
        process_files(listname, [args.file], args)

    else:
        # scan full archive or one list
        pattern = '/a/www/ietf-mail-archive/web/{}/current/'.format(args.list)
        dirs = glob.glob(pattern)
        process_dirs(dirs, args)

    # print "Errors: %d" % errors
    print("message_count: %d" % MESSAGE_COUNT)
    print("match_count: %d" % MATCH_COUNT)
    print("created_count: %d" % CREATED_COUNT)
    print("NO IDs: %d" % NOID)


if __name__ == "__main__":
    main()
