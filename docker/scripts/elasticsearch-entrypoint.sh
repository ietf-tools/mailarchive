#!/bin/bash

echo "Creating keystore..."
bin/elasticsearch-keystore create

echo "Setting azure client..."
echo "$(printenv AZURE_BACKUP_ACCOUNT)" | bin/elasticsearch-keystore add --stdin --force azure.client.default.account
echo "$(printenv AZURE_BACKUP_KEY)" | bin/elasticsearch-keystore add --stdin --force azure.client.default.key

echo "Listing keystore entries..."
bin/elasticsearch-keystore list

echo "Starting elasticsearch entrypoint..."
/usr/local/bin/docker-entrypoint.sh "$@"