#!../../../env/bin/python
"""
In some cases the Python 3 email module folds header lines through the use
of encoded words. Find messages where Archived-At header got folded this 
way and restore unaltered source file 
"""
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import email
import glob
import re
import os
import shutil

from django.conf import settings
from mlarchive.archive.models import Message
from mlarchive.archive.mail import MessageWrapper


BASE_DIR = '/a/mailarch/data/90days'
groups = ['bgp-autoconf', 'tools-development', 'iot-directorate', 'recentattendees',
    'ipr-announce', 'dmarc-report', 'irtf-discuss', 'multipathtcp', 'tools-arch',
    'rfced-ietf', 'new-wg-docs', 'httpbisa', 'ietf-nomcom', 'nethistory', 'crypto-panel',
    'secdispatch', 'privacy-pass', 'teas-3272bis-design-team', 'cwt-reg-review',
    'ietf-community-india', 'ietf-languages', 'rfp-announce', 'wellknown-uri-review',
    'tls-reg-review', 'eligibility-discuss', 'sandbox-mailoutput', 'gendispatch',
    'django-project', 'codesprints', 'dns-privacy', 'iesg-only-2019', 'irtf-announce',
    'yang-doctors', 'quic-issues', 'iot-onboarding', 'architecture-discuss', 'media-types',
    'webtransport', 'rfc-markdown', 'ietf-and-github', 'ietf107-team', 'captive-portals',
    'ippm-ioam-ix-dt', 'manycouches', 'rdma-cc-interest', 'xml2rfc-dev', 'ieee-ietf-coord',
    'ietf-announce', 'ie-doctors', 'sponsorship-team', 'teas-ns-dt', 'iesg-agenda-dist',
    '107attendees', 'i-d-announce', 'netmod-ver-dt', 'tools-discuss', 'mentoring-coordinators']


def get_hash(listname, msg):
    '''Returns the archive hash of message file'''
    mw = MessageWrapper(msg, listname)
    return mw.get_hash()


def get_archive_path(path, group):
    '''Returns full path of archive message file, ie archive/dnsop/Sjsdfsjh238d8fu283,
    given path of source message'''
    with open(path, 'rb') as fp:
        msg = email.message_from_binary_file(fp)
    msg_hash = get_hash(group, msg)
    return '/a/mailarch/data/archive/{}/{}'.format(group, msg_hash)


def main():
    parser = argparse.ArgumentParser(description='Fix corrupted messages')
    parser.add_argument('-c', '--check', help="check only", action='store_true')
    args = parser.parse_args()
    total = 0
    notfound = 0

    for group in groups:
        files = glob.glob('{}/{}.*'.format(BASE_DIR, group))
        for file in files:
            src = os.path.join(BASE_DIR, file)
            archive_path = get_archive_path(src, group)
            if os.path.exists(archive_path):
                total += 1
                print('Copying {} to {}'.format(src, archive_path))
                if not args.check:
                    shutil.copyfile(src, archive_path)
            else:
                print(f'Not found {src}')
                notfound += 1

    print(f'Total: {total}')
    print(f'Not Found: {notfound}')


if __name__ == "__main__":
    main()
