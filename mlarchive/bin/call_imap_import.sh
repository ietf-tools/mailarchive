#!/bin/bash

# call_imap_import.sh

# Script to import list configurations into IMAP server config and reload the server
# Stage in Mail Archive scripts directory
# run as root or with sudo

EXPORT_FILE=/a/mailarch/data/export/email_lists.xml
BACKUP_FILE=$EXPORT_FILE.bak
NOW=$(date +"%Y%m%d")
DATE=$(date)

if [ -f $EXPORT_FILE ]; then
    cp /etc/isode/ms.conf /etc/isode/ms.conf.$NOW
    /opt/isode/sbin/msadm shared_folder import $EXPORT_FILE
    /etc/isode/mbox reload
    mv $EXPORT_FILE $BACKUP_FILE
    echo "$DATE: called msadm shared_folder import" >> /var/isode/log/import.log
fi

    

