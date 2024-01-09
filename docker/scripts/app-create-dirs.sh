#!/bin/bash

for sub in \
    /data/archive \
    /data/log/mail-archive \
    ; do
    if [ ! -d "$sub"  ]; then
        echo "Creating dir $sub"
        mkdir -p "$sub";
    fi
    sudo chown -R dev:dev "/data"
done