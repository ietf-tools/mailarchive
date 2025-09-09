# Instructions for adding blobdb app

- add app to INSTALLED_APPS
- add python dependencies: django-admin-rangefilter, django-storages
- add settings 
  - STORAGES
  - ENABLE_BLOBSTORAGE
  - BLOBSTORAGE_MAX_ATTEMPTS
  - BLOBSTORAGE_CONNECT_TIMEOUT
  - BLOBSTORAGE_READ_TIMEOUT
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
