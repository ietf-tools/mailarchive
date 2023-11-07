#!/a/mailarch/current/env/bin/python

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
import email
import getpass
import logging
import logging.handlers
import socket
import sys
import traceback
from subprocess import Popen, PIPE, STDOUT
    

MAILARCH = '/a/mailarch/current/backend/mlarchive/bin/archive-mail.py'
MAILTO = ['rcross@amsl.com']    # send errors to these addrs


def handle_error(error):
    """Sends an email with error message to appropriate parties"""
    fromaddr = '{}@{}'.format(getpass.getuser(), socket.getfqdn())
    logger = logging.getLogger()
    handler = logging.handlers.SMTPHandler(mailhost=("localhost", 25),
                                           fromaddr=fromaddr,
                                           toaddrs=MAILTO,
                                           subject="MAILMAN ARCHIVE FAILURE ({})".format(' '.join(sys.argv)))
    logger.addHandler(handler)
    logger.error(error)
    

new_args = sys.argv[1:]

if len(new_args) > 1 and new_args[1] not in ('--public', '--private'):     # dump unsupported options
    new_args.pop(1)

data = sys.stdin.buffer.read()

try:
    msg = email.message_from_bytes(data)
    msg_details = 'Message Details:\nFrom:{}\nDate:{}\nMessage ID:{}\n\n'.format(msg.get('from'), msg.get('date'), msg.get('message-id'))
except Exception:
    msg_details = 'Message Details:\n(not available)'


command = ['/a/mailarch/current/env/bin/python', MAILARCH] + new_args
cwd = '/a/mailarch/current/backend/mlarchive/bin'
try:
    p = Popen(command, stdin=PIPE, stdout=PIPE, stderr=STDOUT, cwd=cwd)
    (stdoutdata, stderrdata) = p.communicate(input=data)
    if p.returncode != 0:
        handle_error('script failed: {}\n\n (exit_code={})\n\n {}\n\n{}'.format(command[0], p.returncode, stdoutdata, msg_details))
except Exception:
    handle_error(traceback.format_exc())
    
sys.exit(0)
