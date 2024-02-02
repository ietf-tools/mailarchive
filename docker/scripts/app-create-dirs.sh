#!/bin/bash

for sub in \
    /data/archive \
    /data/incoming \
    /data/import \
    /data/export \
    /data/archive_mbox \
    /data/log/mail-archive \
    ; do
    if [ ! -d "$sub"  ]; then
        echo "Creating dir $sub"
        mkdir -p "$sub";
    fi
    sudo chown -R dev:dev "/data"
done