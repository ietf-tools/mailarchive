#!/bin/bash

# cron_backup.sh

# This script should be run as root regularly (every 5 minutes)
# to find new message files and copy them to the remote backup server

BACKUP_HOST=ietfb.amsl.com
ROOTDIR=/a/mailarch/data/

cd $ROOTDIR
/usr/bin/find ./archive -cmin -7 -type f -print0 | /usr/bin/rsync -a --files-from=- --from0 . $BACKUP_HOST:$ROOTDIR

