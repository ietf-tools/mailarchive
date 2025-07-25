#!/bin/bash

echo "$(printenv AZURE_BACKUP_ACCOUNT)" | bin/elasticsearch-keystore add --stdin --force azure.client.default.account
echo "$(printenv AZURE_BACKUP_KEY)" | bin/elasticsearch-keystore add --stdin --force azure.client.default.key
bin/elasticsearch-keystore list

/usr/local/bin/docker-entrypoint.sh "$@"