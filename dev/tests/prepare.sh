#!/bin/bash

echo "Running containers:"
docker ps -a

echo "Fixing permissions..."
chmod -R 777 ./

echo "Copying config files..."
cp ./dev/tests/test.py ./backend/mlarchive/settings/test.py

echo "Ensure all requirements.txt packages are installed..."
pip --disable-pip-version-check --no-cache-dir install -r requirements.txt

echo "Install chromium for playwright"
playwright install-deps chromium
playwright install chromium

echo "Creating data directories..."
chmod +x ./docker/scripts/app-create-dirs.sh
./docker/scripts/app-create-dirs.sh
