#!/bin/bash

# append path
export PYTHONPATH="$PYTHONPATH:/workspace/backend"

# set required variables
export LOG_DIR='/data'

# Copy temp settings
cp build/app/settings_collectstatics.py backend/mlarchive/settings/
cp docker/configs/docker_env .env

# Install Python dependencies
pip --disable-pip-version-check --no-cache-dir install -r requirements.txt

# Pre create Cloudflare worker templates
# backend/manage.py create_cf_worker_templates --settings=mlarchive.settings.settings_collectstatics

# Collect statics
backend/manage.py collectstatic --settings=mlarchive.settings.settings_collectstatics

# Delete temp local settings
rm backend/mlarchive/settings/settings_collectstatics.py
rm .env
