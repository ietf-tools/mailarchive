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

import getpass
import logging
import logging.handlers
import os
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


path = sys.argv[1]
with open(path, 'rb') as f:
    data = f.read()

listname, access, _ = os.path.basename(path).split('.')
old_args = [listname, '-' + access]
new_args = [listname, '--' + access]


command = ['/a/mailarch/current/env/bin/python', MAILARCH] + new_args
cwd = '/a/mailarch/current/backend/mlarchive/bin'
try:
    p = Popen(command, stdin=PIPE, stdout=PIPE, stderr=STDOUT, cwd=cwd)
    (stdoutdata, stderrdata) = p.communicate(input=data)
    if p.returncode != 0:
        handle_error('script failed: {}\n\n (exit_code={})\n\n {}\n\n{}'.format(command[0], p.returncode, stdoutdata, path))
except Exception:
    handle_error(traceback.format_exc())
    
sys.exit(0)
