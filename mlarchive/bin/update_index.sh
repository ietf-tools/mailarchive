#!/bin/bash

# update_index.sh (for backup server)

# To be run by cron on the backup server
# Updates the Mail Archive index with messages that have
# been added in the last 8 days.  Only rebuild if index 
# is stale, older then 2 days (if this is the live server
# the index will be current)

if [[ ! -n $(find /a/mailarch/data/archive_index -mtime -2) ]]
then
  cd /a/mailarch/current/
  source bin/activate
  export PYTHONPATH=$PWD
  django-admin.py update_index --age=192 --batch-size=10000 --settings=mlarchive.settings.production
fi
