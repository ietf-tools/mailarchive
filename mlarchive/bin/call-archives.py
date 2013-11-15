#!/usr/bin/python
'''
The purpose of this script is to allow mailman to use multiple archiving systems.
The script should be configured in mm_cfg.py as follows:

PUBLIC_EXTERNAL_ARCHIVER = '/a/ietf/scripts/call-archives.py %(listname)s --public'
PRIVATE_EXTERNAL_ARCHIVER = '/a/ietf/scripts/call-archives.py %(listname)s --private'

The script will save STDIN and use it to make calls to both archive systems.  It first calls the
mhonarc system.  If that fails we return exit code of the mhonarc script, allowing for retries
from mailman.  If it succeeds we proceed to the mail archive.

When the time comes to end parallel archiving this script should be replaced by one that
stashes the message, queues the import, and notifies on any failures
'''
import os
import subprocess
import sys

MHONARC = '/a/ietf/scripts/archive-mail.pl'
MAILARCH= '/a/mailarch/current/mlarchive/bin/archive-mail.py'

args = sys.argv[1:]
data = sys.stdin.read()

p = subprocess.Popen([MHONARC, args[0], args[1][1:]], stdin=subprocess.PIPE)    # strip dash
p.communicate(input=data)
if p.returncode != 0:
    sys.exit(p.returncode)

if os.path.exists('/a/mailarch/data/mailman.enable'):
    p = subprocess.Popen([MAILARCH] + args, stdin=subprocess.PIPE)
    p.communicate(input=data)

sys.exit(0)
