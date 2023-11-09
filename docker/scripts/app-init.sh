#!/bin/bash

WORKSPACEDIR="/workspace"

sudo service rsyslog start &>/dev/null

# Fix ownership of volumes
echo "Fixing volumes ownership..."
sudo chown -R dev:dev "$WORKSPACEDIR/.parcel-cache"
sudo chown -R dev:dev "$WORKSPACEDIR/__pycache__"
sudo chown dev:dev "/data"

echo "Fix chromedriver /dev/shm permissions..."
sudo chmod 1777 /dev/shm

# Build node packages that requrie native compilation
# echo "Compiling native node packages..."
# yarn rebuild

# Generate static assets
# echo "Building static assets... (this could take a minute or two)"
# yarn build

# Copy config files if needed

if [ ! -f "$WORKSPACEDIR/.env" ]; then
    echo "Setting up a default .env ..."
    cp $WORKSPACEDIR/docker/configs/docker_env $WORKSPACEDIR/.env
else
    echo "Using existing .env file"
    if ! cmp -s $WORKSPACEDIR/docker/configs/docker_env $WORKSPACEDIR/.env; then
        echo "NOTE: Differences detected compared to docker/configs/docker_env!"
        echo "We'll assume you made these deliberately."
    fi
fi

if [ ! -f "$WORKSPACEDIR/backend/mlarchive/settings/settings_docker.py" ]; then
    echo "Setting up a default settings_docker.py ..."
else
    echo "Renaming existing backend/mlarchive/settings/settings_docker.py to backend/mlarchive/settings/settings_docker.py.bak"
    mv -f $WORKSPACEDIR/backend/mlarchive/settings/settings_docker.py $WORKSPACEDIR/backend/mlarchive/settings/settings_docker.py.bak
fi
cp $WORKSPACEDIR/docker/configs/settings_docker.py $WORKSPACEDIR/backend/mlarchive/settings/settings_docker.py

# Create data directories
echo "Creating data directories..."
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

echo "-----------------------------------------------------------------"
echo "Done!"
echo "-----------------------------------------------------------------"

if [ -z "$EDITOR_VSCODE" ]; then
    CODE=0
    python -m smtpd -n -c DebuggingServer localhost:2025 &
    if [ -z "$*" ]; then
        echo
        echo "You can execute arbitrary commands now, e.g.,"
        echo
        echo "    backend/manage.py check && backend/manage.py runserver 0.0.0.0:8000"
        echo
        echo "to start a development instance of the Datatracker."
        echo
        echo "    cd backend/mlarchive && pytest tests"
        echo
        echo "to run all the tests."
        echo
        zsh
    else
        echo "Executing \"$*\" and stopping container."
        echo
        zsh -c "$*"
        CODE=$?
    fi
    sudo service rsyslog stop
    exit $CODE
fi
