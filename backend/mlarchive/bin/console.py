#!../../../env/bin/python
'''
Script to gather some archive statistics and save them in a file for use on the console page.
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
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
