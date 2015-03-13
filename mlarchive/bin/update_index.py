#!/usr/bin/python
'''
update_index script to be run on the backup server where there isn't live indexing.
Checks the time of the index files and calls update_index with appropriate arguments
to bring the index current.  Can be run from cron regularly to keep index somewhat
fresh, or from command line to bring index current during a failover.
'''
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
import django
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.production'
django.setup()

# -------------------------------------------------------------------------------------

# get time of index
