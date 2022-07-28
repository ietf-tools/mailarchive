#!/usr/bin/sh

# This is a bare-bones shell wrapper script for the archive import script
# This script reads a message from stdin, immediately writes it to disk for 
# safe keeping, then calls a script to archive the message. It is customized
# to work with piped input from postfix.
# NOTE: all messages get saved with "private" designator. The designator
# is only used for lists new to the archives. Existing lists retain their
# current permissions (public|private).

# This script is called from /a/postfix/aliases.  Example:

# ietfarch-ietf-archive:          '|/a/mailarch/current/backend/mlarchive/bin/call-archives-pipe.sh ietf'

# save message
FILE=`/usr/bin/mktemp -u --tmpdir=/a/mailarch/data/incoming $1.private.XXXXXXXX`
cat > $FILE

# archive message
/a/mailarch/current/backend/mlarchive/bin/call-archives.py $FILE
