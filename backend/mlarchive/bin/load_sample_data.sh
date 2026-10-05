#!/bin/bash

# script to load sample data in a development system

cd /assets

# Check if the directory exists
if [[ ! -d /assets/import ]]; then
    mkdir -p /assets/import
fi


cd import

# load email list data
if [[ -f /assets/import/emaillists.csv ]]; then
    echo "Loading Email Lists"
    psql -h db -d mailarch -U django -c "copy archive_emaillist from '/assets/import/emaillists.csv' DELIMITER E'\t'"
else
    echo "emaillists.csv not found"
fi

# rsync mbox files
rsync -a \
    --include='yang-doctors/***' \
    --include='mtgvenue/***' \
    --include='curdle/***' \
    --exclude='*' \
    rsync.ietf.org::mailman-archive/ \
    ./

# load messages
cd /workspace/backend/mlarchive/bin
python ./loader.py /assets/import

# load subscriber info
if [[ -f /assets/import/subscribers.csv ]]; then
    echo "Loading Subscribers"
    psql -h db -d mailarch -U django -c "copy archive_subscriber from '/assets/import/subscribers.csv' DELIMITER E'\t'"
else
    echo "subscribers.csv not found"
fi