#!/bin/bash

echo "Running Mailarchive checks..."
./backend/manage.py check

echo "Running Mailarchive migrations..."
./backend/manage.py migrate

echo "Running Initializing index..."
./backend/manage.py init_index

echo "Starting Mailarchive..."

# trap TERM and shut down gunicorn
cleanup () {
    if [[ -n "${gunicorn_pid}" ]]; then
        echo "Terminating gunicorn..."
        kill -TERM "${gunicorn_pid}"
        wait "${gunicorn_pid}"
    fi
}

trap 'trap "" TERM; cleanup' TERM

# start gunicorn in the background so we can trap the TERM signal
gunicorn \
          --workers "${GUNICORN_WORKERS:-9}" \
          --max-requests "${GUNICORN_MAX_REQUESTS:-32768}" \
          --timeout "${GUNICORN_TIMEOUT:-180}" \
          --log-level "${GUNICORN_LOG_LEVEL:-info}" \
          --bind :8000 \
          --capture-output \
          --access-logfile -\
          ${GUNICORN_EXTRA_ARGS} \
          backend.mlarchive.wsgi:application &
gunicorn_pid=$!
wait "${gunicorn_pid}"
