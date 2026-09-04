# Copyright The IETF Trust 2026, All Rights Reserved
"""One-time backfill of StoredObject rows for blobs written before the metadata layer.

Everything here is temporary. Once the historical corpus has been indexed in
production this module, its test module and the registration import in
archive/tasks.py are deleted together. It is the one place outside mlarchive/blobdb
that imports the Blob model, because the backfill walks the whole Blob table by
global pk across buckets, which nothing in the Storage API can express.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db.models.functions import Length
from django.utils.module_loading import import_string

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage import StoredObjectBlobdbStorage
from mlarchive.blobdb.models import Blob

logger = logging.getLogger(__name__)

BACKFILL_STORED_OBJECTS_STOP_KEY = 'backfill_stored_objects_stop'


def tracked_buckets():
    """Return the blobdb bucket names whose storage records StoredObject rows."""
    buckets = []
    for config in settings.STORAGES.values():
        backend = import_string(config['BACKEND'])
        if issubclass(backend, StoredObjectBlobdbStorage):
            buckets.append(config['OPTIONS']['bucket_name'])
    return buckets


def backfill_stored_objects(start_after_pk=0, batch_size=5000):
    """Index one batch of pre-existing blobs as StoredObject rows."""

    rows = list(
        Blob.objects
        .filter(pk__gt=start_after_pk, bucket__in=tracked_buckets())
        .order_by('pk')
        .annotate(object_size=Length('content'))
        .values_list('pk', 'bucket', 'name', 'checksum', 'object_size', 'modified')
        [:batch_size]
    )
    if not rows:
        return None

    existing = set()
    for bucket in {row[1] for row in rows}:
        names = [row[2] for row in rows if row[1] == bucket]
        existing.update(
            StoredObject.objects
            .filter(store=bucket, name__in=names)
            .values_list('store', 'name')
        )

    records = [
        StoredObject(
            store=bucket,
            name=name,
            sha384=checksum,
            len=object_size,
            store_created=modified,
            created=modified,
            modified=modified,
        )
        for _, bucket, name, checksum, object_size, modified in rows
        if (bucket, name) not in existing
    ]
    # ignore_conflicts covers a row written by the storage between the existence
    # check and the insert; the explicit batch_size keeps each INSERT within the
    # Postgres parameter limit regardless of the caller's batch size.
    StoredObject.objects.bulk_create(records, batch_size=1000, ignore_conflicts=True)

    return {
        'last_pk': rows[-1][0],
        'created': len(records),
        'skipped': len(rows) - len(records),
    }


@shared_task
def backfill_stored_objects_task(start_after_pk=0, batch_size=5000, countdown=5):
    """Index one batch of pre-existing blobs as StoredObject rows, then self-chain.

    One-time work to bring the historical corpus into the StoredObject table; new
    writes are tracked by the storage itself. Dispatched by hand rather than by Beat,
    on the blobdb queue so it never competes with indexing on the default queue.

    To kick off:   backfill_stored_objects_task.apply_async(queue='blobdb')
    To stop:       cache.set('backfill_stored_objects_stop', True, timeout=None)
    To resume:     cache.delete('backfill_stored_objects_stop')
                   backfill_stored_objects_task.apply_async(
                       queue='blobdb', kwargs={'start_after_pk': <last logged pk>})
    """
    if cache.get(BACKFILL_STORED_OBJECTS_STOP_KEY):
        logger.info(
            'backfill_stored_objects: halted by stop flag, resume with start_after_pk=%d',
            start_after_pk)
        return

    result = backfill_stored_objects(start_after_pk=start_after_pk, batch_size=batch_size)
    if result is None:
        logger.info('backfill_stored_objects: complete, last_pk=%d', start_after_pk)
        return

    logger.info(
        'backfill_stored_objects: batch done, last_pk=%d, created=%d, skipped=%d',
        result['last_pk'], result['created'], result['skipped'])

    backfill_stored_objects_task.apply_async(
        kwargs=dict(
            start_after_pk=result['last_pk'],
            batch_size=batch_size,
            countdown=countdown,
        ),
        countdown=countdown,
        queue='blobdb',
    )
