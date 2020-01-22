#!../../../env/bin/python
'''
Script to output some stats about the archive.  Run from cron and email to someone:

MAILTO="rcross@amsl.com"
10 00 * * * /a/mailarch/current/mlarchive/bin/stats.py
'''

# Standalone broilerplate -------------------------------------------------------------
from .django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import datetime
import subprocess

from mlarchive.archive.models import Message

POST_LOG = '/a/mailman/logs/post'

today = datetime.date.today()
yesterday = today - datetime.timedelta(days=1)
str = yesterday.strftime("%b %d")
posts = 0

with open(POST_LOG) as f:
    for line in f.readlines():
        if line.startswith(str):
            posts += 1

recs = Message.objects.filter(updated__gte=yesterday,updated__lt=today).count()
output = subprocess.check_output(['delve','/a/mailarch/data/archive_index'])
index = output.split('\n')[1].split()[-1]

print('mailmam posts: %d' % posts)
print('db records: %d' % recs)
print('index records: %s' % index)

