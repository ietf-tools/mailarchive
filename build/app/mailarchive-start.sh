#!/bin/bash

echo "Running Mailarchive checks..."
./backend/manage.py check

echo "Running Mailarchive migrations..."
./backend/manage.py migrate

echo "Running Initializing index..."
./backend/manage.py init_index

echo "Starting Mailarchive..."
./backend/manage.py runserver 0.0.0.0:8000