#!/bin/bash

# script to load some small lists into the archive

INCLUDE_FILE="rsync_include.txt"

cd /tmp

# create rsync include file
cat > "$INCLUDE_FILE" <<EOL
yang-doctors/***
mtgvenue/***
curdle/***
EOL

# sync
rsync -av --include-from="$INCLUDE_FILE" --exclude='*' rsync.ietf.org::mailman-archive/ ./

# load data
cd /workspace/backend
./manage.py load /tmp/yang-doctors/2018-10.mail
./manage.py load /tmp/curdle/2017-05.mail
./manage.py load /tmp/mtgvenue/2016-07.mail