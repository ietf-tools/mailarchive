#!/usr/bin/python
'''
The purpose of this script is to allow mailman to use multiple archiving systems.
The script should be configured in mm_cfg.py as follows:

PUBLIC_EXTERNAL_ARCHIVER = '/a/ietf/scripts/call-archives.py %(listname)s --public'
PRIVATE_EXTERNAL_ARCHIVER = '/a/ietf/scripts/call-archives.py %(listname)s --private'

This script is also called from /a/postfix/aliases.  Example:

ietfarch-itu+ietf-web-archive:          "|/a/ietf/scripts/call_archives.py itu+ietf -web"

The script will save STDIN and use it to make calls to both archive systems.
It first calls the mhonarc system then the new archiver.  If either fail handle_error()
is called.

When the time comes to end parallel archiving this script should be replaced by one that
stashes the message, queues the import, and notifies on any failures
'''
import getpass
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import traceback
    
MHONARC = '/a/ietf/scripts/archive-mail.pl'
MAILARCH= '/a/mailarch/current/mlarchive/bin/archive-mail.py'
MAILTO = ['rcross@amsl.com','jshaffer@amsl.com']    # send errors to these addrs

def handle_error(error):
    """Sends an email with error message to appropriate parties"""
    fromaddr = '{}@{}'.format(getpass.getuser(),socket.getfqdn())
    logger = logging.getLogger()
    handler = logging.handlers.SMTPHandler(mailhost=("localhost",25),
                                           fromaddr=fromaddr,
                                           toaddrs=MAILTO,
                                           subject="MAILMAN ARCHIVE FAILURE ({})".format(' '.join(sys.argv)))
    logger.addHandler(handler)
    logger.error(error)
    
old_args = sys.argv[1:]
new_args = old_args[:]

if len(old_args) > 1:
    if old_args[1].startswith('--'):                    # convert to single dash
        old_args[1] = old_args[1][1:]
    if new_args[1] not in ('--public','--private'):     # dump unsupported options
        new_args.pop(1)

data = sys.stdin.read()

try:
    p = subprocess.Popen([MHONARC] + old_args, stdin=subprocess.PIPE)
    p.communicate(input=data)
    if p.returncode != 0:
        handle_error('script failed: {} (exit_code={})'.format(MHONARC,p.returncode))
except Exception as error:
    handle_error(traceback.format_exc())
    
try:
    p = subprocess.Popen([MAILARCH] + new_args, stdin=subprocess.PIPE)
    p.communicate(input=data)
    if p.returncode != 0:
        handle_error('script failed: {} (exit_code={})'.format(MAILARCH,p.returncode))
except Exception as error:
    handle_error(traceback.format_exc())

sys.exit(0)
