#!/bin/bash

# script to load legacy archive messages that have changed 
# set reference time this way: touch -t 201312130000.00 /tmp/ref

export PYTHONPATH=/a/mailarch/current
cd /a/mailarch/current

FILES=`find /a/www/ietf-mail-archive/text/ -newer /tmp/ref -type f -print`
for f in $FILES
do
    d=`echo $f|awk -F'/' '{print $6}'`
    echo -n "---- loading: "
    echo $f
    ./manage.py load $f -l $d
done
