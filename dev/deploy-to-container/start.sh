#!/bin/bash

echo "Creating /data directories..."
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
done
echo "Fixing permissions..."
chmod -R 777 ./
echo "Ensure all requirements.txt packages are installed..."
pip --disable-pip-version-check --no-cache-dir install -r requirements.txt
echo "Creating data directories..."
chmod +x ./app-create-dirs.sh
./app-create-dirs.sh

if [ -n "$PGHOST" ]; then
    echo "Altering PG search path..."
    psql -U django -h $PGHOST -d mailarchive -v ON_ERROR_STOP=1 -c '\x' -c 'ALTER USER django set search_path=mailarchive,public;'
fi

echo "Starting memcached..."
/usr/bin/memcached -d -u root

echo "Running Mail Archive checks..."
./backend/manage.py check

echo "Running Mail Archive migrations..."
 ./backend/manage.py migrate --settings=mlarchive.settings.settings_sandbox

until nc -z -w 5 "$ELASTICSEARCH_HOST" 9200; do
  echo "Waiting for Elasticsearch..."
  sleep 5
done

echo "Initializing index..."
./backend/manage.py init_index

echo "Loading sample data..."
./load_data.sh

echo "Starting Mail Archive..."
./backend/manage.py runserver 0.0.0.0:8000 --settings=mlarchive.settings.settings_sandbox
