#!/usr/bin/sh

export DJANGO_SETTINGS_MODULE=mlarchive.settings
cd /a/home/rcross/src/amsl/mailarch/trunk

HOST=`hostname`
if [ "$HOST" = "ietfb" ]; then
    touch /a/home/rcross/data/log/ietfb.log
    #./bin/loader.py -t -f
fi
