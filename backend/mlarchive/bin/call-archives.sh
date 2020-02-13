#!/bin/bash

# This script reads a message from stdin, immediately writes it to disk, then
# calls a script to archive the message.

# The script should be configured for mailman as follows:
# /usr/lib/mailman/Mailman/mm_cfg.py

# PUBLIC_EXTERNAL_ARCHIVER = '/a/mailarch/current/backend/mlarchive/bin/call-archives.sh %(listname)s --public'
# PRIVATE_EXTERNAL_ARCHIVER = '/a/mailarch/current/backend/mlarchive/bin/call-archives.sh %(listname)s --private'

# This script is also called from /a/postfix/aliases.  Example:

# ietfarch-itu+ietf-web-archive:          '|/a/mailarch/current/backend/mlarchive/bin/call-archives.sh itu+ietf -web'

PATH=/a/mailarch/data/incoming
PROG=/a/mailarch/current/backend/mlarchive/bin/call-archives.py

if [ "$2" = "--private" ]; then
    TYPE="private"
else
    TYPE="public"
fi

# save message
FILE=`/usr/bin/mktemp --tmpdir=$PATH $1.$TYPE.XXXXXXXX`
/usr/bin/cp /dev/stdin $FILE

# archive message
$PROG $FILE

