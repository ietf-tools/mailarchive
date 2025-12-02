# Instructions for adding blobdb app

- add app to INSTALLED_APPS
- add python dependencies: django-admin-rangefilter, django-storages, botocore, boto3, boto3-stubs
- add settings 
  - STORAGES
  - ENABLE_BLOBSTORAGE
  - BLOB_STORE_ENDPOINT_URL
  - BLOB_STORE_SECRET_KEY
  - BLOB_STORE_ACCESS_KEY
  - BLOB_STORE_CONNECT_TIMEOUT
  - BLOB_STORE_READ_TIMEOUT
  - BLOB_STORE_MAX_ATTEMPTS
  - BLOB_STORE_BUCKET_PREFIX
  - BLOB_STORE_ENABLE_PROFILING
  - BLOBDB_DATABASE
  - BLOBDB_REPLICATION
  - CELERY_TASK_ROUTES
  - DATABASE_ROUTERS
  - DATABASES, add blobdb
- containers to docker-compose as needed
  - blobstore
  - blobdb

# References
- https://docs.djangoproject.com/en/5.2/ref/files/storage/
