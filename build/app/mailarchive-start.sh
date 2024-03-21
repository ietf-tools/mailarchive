#!/bin/bash

echo "Running Mailarchive checks..."
./backend/manage.py check

echo "Running Mailarchive migrations..."
./backend/manage.py migrate

echo "Running Initializing index..."
./backend/manage.py init_index

echo "Starting Mailarchive..."
gunicorn \
          --workers 10 \
          --max-requests 32768 \
          --timeout 180 \
          --log-level info \
          --bind :8000 \
          backend.mlarchive.wsgi:application
