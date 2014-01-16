#!/usr/bin/python
'''
Script to gather some archive statistics and save them in a file for use on the console page.
'''

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
import json
import subprocess
from django.conf import settings

data = {}
output = subprocess.check_output(['delve',settings.HAYSTACK_XAPIAN_PATH])
data['index_records'] = output.split('\n')[1].split()[-1]

with open(settings.CONSOLE_STATS_FILE, 'a') as outfile:
  json.dump(data, outfile)