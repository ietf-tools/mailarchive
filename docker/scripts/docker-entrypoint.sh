#!/usr/bin/env bash

# do some setup, migrate, etc
#

WORKSPACEDIR="/workspace"

# add path of dev local python bin
export PATH="$PATH:/home/dev/.local/bin"

sudo service rsyslog start &>/dev/null

# Fix ownership of volumes
echo "Fixing volumes ownership..."
sudo chown -R dev:dev "$WORKSPACEDIR"
sudo chown dev:dev "/data"

echo "Fix chromedriver /dev/shm permissions..."
sudo chmod 1777 /dev/shm

# Create data directories
echo "Creating data directories..."
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


# Wait for DB container

if [ -n "$EDITOR_VSCODE" ]; then
    echo "Waiting for DB container to come online ..."
    /usr/local/bin/wait-for localhost:5432 -- echo "DB ready"
fi

# Run memcached

echo "Starting memcached..."
/usr/bin/memcached -u dev -d

# Initial checks

echo "Running initial checks..."
/usr/local/bin/python $WORKSPACEDIR/backend/manage.py check
/usr/local/bin/python $WORKSPACEDIR/backend/manage.py migrate


exec "$@"
