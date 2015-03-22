#!/bin/bash

# call_imap_import.sh

# Script to import list configurations into IMAP server config and reload the server
# Stage in Mail Archive scripts directory
# NOTE: user will need appropriate sudo permissions

DATA_ROOT=/a/mailarch/data

sudo /opt/isode/sbin/msadm shared_folder import $DATA_ROOT/export/email_lists.xml
sudo /etc/isode/mbox reload