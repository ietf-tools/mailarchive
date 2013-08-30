#!/usr/bin/python
'''
The purpose of this script is to allow mailman to use multiple archiving systems.
The script should be configured in mm_cfg.py as follows:

PUBLIC_EXTERNAL_ARCHIVER = '/a/mailarch/current/mlarchive/bin/call-archives.py %(listname)s -public'
PRIVATE_EXTERNAL_ARCHIVER = '/a/mailarch/current/mlarchive/bin/call-archives.py %(listname)s -private'

Be sure to use the correct path.  The script will save STDIN and use it to make calls to both
archive systems.  It first calls the mhonarc system.  If that fails we return exit code of the
mhonarc script, allowing for retries from mailman.  If it succeeds we proceed to the mail archive,
logging errors to syslog.
'''

import subprocess
import sys
import syslog

MHONARC = '/a/ietf/scripts/archive-mail.pl'
MAILARCH= '/a/mailarch/current/mlarchive/bin/archive-mail.py'

args = sys.argv[1:]
data = sys.stdin.read()

p = subprocess.Popen([MHONARC] + args, stdin=subprocess.PIPE)
p.communicate(input=data)
if p.returncode != 0:
    sys.exit(p.returncode)

p = subprocess.Popen([MAILARCH] + args, stdin=subprocess.PIPE)
p.communicate(input=data)
if p.returncode != 0:
    syslog.syslog(syslog.LOG_MAIL | syslog.LOG_ERR,
        'archive message failed ({0}) ({1})'.format(p.returncode,data.splitlines()[0]))

