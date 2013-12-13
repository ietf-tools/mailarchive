#!/usr/bin/python

# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings'
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

print 'mailmam posts: %d' % posts
print 'db records: %d' % recs
print 'index records: %s' % index

