#!/bin/bash
#
# Run a celery worker
#
# echo "Running Mailarchive checks..."
# ./backend/manage.py check

celery "$@"
