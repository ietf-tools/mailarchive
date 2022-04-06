#!/a/mailarch/current/env/bin/python

'''
The purpose of this script is to allow mailman to use multiple archiving systems.

The script takes one input argument, the full path to the message file. It should
have a syntax like:

[listname].[public|private].[unique value]

The script will make appropriate calls to both archive systems.
It first calls the mhonarc system then the new archiver.  If either fail handle_error()
is called.
'''

import email
import getpass
import logging
import logging.handlers
import os
import socket
import sys
import traceback
from subprocess import Popen, PIPE, STDOUT
    
MHONARC = '/a/ietf/scripts/archive-mail.pl'
MAILARCH= '/a/mailarch/current/backend/mlarchive/bin/archive-mail.py'
MAILTO = ['rcross@amsl.com', 'glen@amsl.com']    # send errors to these addrs

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
    
'''
old_args = sys.argv[1:]
new_args = old_args[:]

if len(old_args) > 1:
    if old_args[1].startswith('--'):                    # convert to single dash
        old_args[1] = old_args[1][1:]
    if new_args[1] not in ('--public','--private'):     # dump unsupported options
        new_args.pop(1)

if hasattr(sys.stdin, 'buffer'):
    data = sys.stdin.buffer.read()
else:
    data = sys.stdin.read()

try:
    msg = email.message_from_string(data)
    msg_details = 'Message Details:\nFrom:{}\nDate:{}\nMessage ID:{}\n\n'.format(msg.get('from'), msg.get('date'), msg.get('message-id'))
except Exception:
    msg_details = 'Message Details:\n(not available)'
'''

path = sys.argv[1]
with open(path, 'rb') as f:
    data = f.read()

listname, access, _ = os.path.basename(path).split('.')
old_args = [listname, '-' + access]
new_args = [listname, '--' + access]

'''
command = [MHONARC] + old_args
try:
    p = Popen(command, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
    (stdoutdata, stderrdata) = p.communicate(input=data)
    if p.returncode != 0:
        handle_error('script failed: {}\n\n (exit_code={})\n\n {}\n\n{}'.format(command[0],p.returncode,stdoutdata, path))
except Exception as error:
    handle_error(traceback.format_exc())
'''

command = ['/a/mailarch/current/env/bin/python', MAILARCH] + new_args
cwd = '/a/mailarch/current/backend/mlarchive/bin'
try:
    p = Popen(command, stdin=PIPE, stdout=PIPE, stderr=STDOUT, cwd=cwd)
    (stdoutdata, stderrdata) = p.communicate(input=data)
    if p.returncode != 0:
        handle_error('script failed: {}\n\n (exit_code={})\n\n {}\n\n{}'.format(command[0],p.returncode,stdoutdata, path))
except Exception as error:
    handle_error(traceback.format_exc())
    
sys.exit(0)
