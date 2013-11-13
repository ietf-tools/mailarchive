#!/bin/bash

export PYTHONPATH=/a/mailarch/current
export DJANGO_SETTINGS_MODULE=mlarchive.settings
cd /a/mailarch/current/mlarchive

if [ ! -f /a/mailarch/lockfile ]; then

    touch /a/mailarch/lockfile
    #./bin/pre-import.py
    #./bin/clear
    mysql --user=rcross --password=sounders43 rc_archiveb < /a/mailarch/data/legacy.sql
    #./bin/loader.py -t -f
    ./bin/loader.py -f
    #rm /a/mailarch/lockfile
else
    echo "STOPPED: lockfile exists"
fi
