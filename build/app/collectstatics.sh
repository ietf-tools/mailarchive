#!/bin/bash

# append path
export PYTHONPATH="$PYTHONPATH:/workspace/backend"

# set required variables
export LOG_DIR="/data"
export SECRET_KEY="django-insecure-+o^#r0fvt!n=h1f6a_a+nt*mfk4(9ipu2bl372q3ys1$_@v46m"

# Copy temp settings
cp build/app/settings_collectstatics.py backend/mlarchive/settings/

# Install Python dependencies
pip --disable-pip-version-check --no-cache-dir install -r requirements.txt

# Collect statics
backend/manage.py collectstatic --settings=mlarchive.settings.settings_collectstatics

# Delete temp local settings
rm backend/mlarchive/settings/settings_collectstatics.py
