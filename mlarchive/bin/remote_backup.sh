#!/bin/bash

# 2015-02-04
# Author: Ryan Cross

# Mail Archive Remote Backup Script
# This script is called by the Mail Archive when messages are 
# written to disk.  $1 = path of message
# Uses rsync to copy the file to a remote backup server.

# For simplicity just run an rsync.  If it fails, the full 
# directory rsync, which runs roughly hourly from ietfb,
# will ensure files are in sync.

REMOTE_HOST=ietfb.amsl.com
ROOTDIR=/a/mailarch/data/archive
BACKDIR=/a/mailarch/data/backup
RELPATH=`echo $1 | cut -c 26-`

cd $ROOTDIR
/usr/bin/rsync -aR --omit-dir-times $RELPATH $REMOTE_HOST:$ROOTDIR

#then
#   # copy any previous failed transfers
#   cd $BACKDIR
#   rsync -aR --omit-dir-times --no-perms --remove-source-files . $REMOTE_HOST:$ROOTDIR 
#else
#   /usr/bin/rsync -aR $RELPATH $BACKDIR
#fi 
