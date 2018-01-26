#!/usr/bin/python
from __future__ import print_function

'''
Script to retrieve active lists, identify inactive lists, and update the db

'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------

import datetime
import subprocess
from mlarchive.archive.models import EmailList


active = []
to_inactive = []

# get active mailman lists
output = subprocess.check_output(['/usr/lib/mailman/bin/list_lists'])
for line in output.splitlines():
    name = line.split(' - ')[0].strip().lower()
    active.append(name)

# get externally hosted lists
output = subprocess.check_output(['grep', 'call-archives.py', '/a/postfix/aliases'])
for line in output.splitlines():
    name = line.split()[-1].strip('"').strip().lower()
    active.append(name)

for elist in EmailList.objects.filter(active=True).order_by('name'):
    if elist.name not in active:
        messages = elist.message_set.all().order_by('-date')
        if messages.first() and messages.first().date > datetime.datetime.today() - datetime.timedelta(days=90):
            print("{}  => inactive.  SKIPPING last message date = {}".format(elist.name, messages.first().date))
            continue
        print("{}  => inactive".format(elist.name))
        to_inactive.append(elist)

answer = raw_input('Update lists y/n?')

if answer.lower() == 'y':
    print('OK')
    EmailList.objects.filter(name__in=to_inactive).update(active=False)