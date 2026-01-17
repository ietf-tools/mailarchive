#!/bin/bash
#
# Environment config:
#
#  CONTAINER_ROLE - mailarchive, celery, or beat (defaults to mailarchive)
#
case "${CONTAINER_ROLE:-mailarchive}" in
    mailarchive)
        exec ./mailarchive-start.sh
        ;;
    celery)
        exec ./celery-start.sh --app="${CELERY_APP:-mlarchive.celeryapp:app}" worker
        ;;
    beat)
        exec ./celery-start.sh --app="${CELERY_APP:-mlarchive.celeryapp:app}" beat
        ;;
    replicator)
        exec ./celery-start.sh --app="${CELERY_APP:-mlarchive.celeryapp:app}" worker --queues=blobdb --concurrency=1
        ;;
    *)
        echo "Unknown role '${CONTAINER_ROLE}'"
        exit 255       
esac