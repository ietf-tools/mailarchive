#!/usr/bin/env python
'''
Process _filtered directory for list. Load messages into archive
and delete from _filtered on success

Usage:

process_filtered LISTNAME
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import os
import shutil
import sys
from email.parser import BytesParser

from django.conf import settings

from mlarchive.archive.models import Message
from mlarchive.archive.mail import archive_message

import logging
# logpath = os.path.join(settings.DATA_ROOT, 'log/process_filtered.log')
# logging.basicConfig(filename=logpath, level=logging.DEBUG)


def main():
    parser = argparse.ArgumentParser(description='Process messages in _filtered')
    parser.add_argument('listname', help='List to process')
    parser.add_argument('--private', action='store_true', default=False, help="The list is private")
    parser.add_argument('--scan', action='store_true', default=False, help="Scan only")
    args = parser.parse_args()
    
    filtered_dir = os.path.join(settings.ARCHIVE_DIR, args.listname, '_filtered')
    dupes_dir = os.path.join(settings.ARCHIVE_DIR, args.listname, '_dupes')

    if not os.path.exists(filtered_dir):
        print(f'{filtered_dir} does not exist')
        sys.exit(1)

    files = os.listdir(filtered_dir)

    print(f'List: {args.listname}')
    print(f'Private: {args.private}')
    print('Count: {}'.format(len(files)))

    if args.scan:
        sys.exit(0)

    process_count = 0
    error_count = 0
    skipped_count = 0
    emailparser = BytesParser()
    for file in files:
        path = os.path.join(filtered_dir, file)
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError as e:
            print(f'Error reading file {e}')
            error_count += 1
            continue
        
        # get message id and precheck
        msg = emailparser.parsebytes(data, headersonly=True)
        msgid = msg.get('message-id').strip('<>')
        if Message.objects.filter(email_list__name=args.listname, msgid=msgid).exists():
            print(f'message already exists in archive {path}')
            skipped_count += 1
            if not os.path.exists(dupes_dir):
                os.mkdir(dupes_dir)
            shutil.move(path, dupes_dir)
            continue

        # process message
        status = archive_message(data, args.listname, private=args.private)
        if status != 0:
            print(f'ERROR: failed to import {path}')
            error_count += 1
            continue

        # confirm message imported and delete from _filtered
        if Message.objects.filter(email_list__name=args.listname, msgid=msgid).exists():
            os.remove(path)
            process_count += 1

    print(f'Total messasges processed: {process_count}')
    print(f'Total errors: {error_count}')
    print(f'Total skipped: {skipped_count}')


if __name__ == "__main__":
    main()
