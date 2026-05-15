# Copyright The IETF Trust 2025, All Rights Reserved

import json
import logging

from celery import shared_task
from django.core.cache import cache

from .replication import replicate_blob, ReplicationError

logger = logging.getLogger(__name__)

MIGRATION_STOP_KEY = 'migrate_messages_to_blobdb_stop'
REBUILD_JSON_STOP_KEY = 'rebuild_messages_json_stop'


@shared_task(
    autoretry_for=(ReplicationError,), retry_backoff=10, retry_kwargs={"max_retries": 5}
)
def pybob_the_blob_replicator_task(body: str):
    request = json.loads(body)
    bucket = request["bucket"]
    name = request["name"]
    replicate_blob(bucket, name)


@shared_task
def migrate_messages_to_blobdb(
    start_after_pk=0,
    batch_size=1000,
    start_date=None,
    end_date=None,
    email_lists=None,
    max_workers=50,
    countdown=30,
):
    """Migrate one batch of Messages to blobdb and replicate to R2, then self-chain.

    Processes one batch of up to batch_size messages and schedules the next batch
    with a countdown delay, so the full migration proceeds without flooding the queue.

    To kick off:   migrate_messages_to_blobdb.apply_async(queue='blobdb')
    To stop:       cache.set('migrate_messages_to_blobdb_stop', True, timeout=None)
    To resume:     cache.delete('migrate_messages_to_blobdb_stop')
                   migrate_messages_to_blobdb.apply_async(queue='blobdb', kwargs={'start_after_pk': <last logged pk>, ...})
    """
    from mlarchive.archive.models import Message
    from mlarchive.archive.utils import migrate_messages_to_blobdb as _migrate_batch

    if cache.get(MIGRATION_STOP_KEY):
        logger.info('migrate_messages_to_blobdb: halted by stop flag, resume with start_after_pk=%d', start_after_pk)
        return

    filters = {'pk__gt': start_after_pk}
    if start_date is not None:
        filters['date__gte'] = start_date
    if end_date is not None:
        filters['date__lt'] = end_date
    if email_lists:
        filters['email_list__name__in'] = email_lists

    batch = list(
        Message.objects
        .select_related('email_list')
        .filter(**filters)
        .order_by('pk')[:batch_size]
    )

    if not batch:
        logger.info('migrate_messages_to_blobdb: complete, last_pk=%d', start_after_pk)
        return

    failures = _migrate_batch(batch, max_workers=max_workers)
    last_pk = batch[-1].pk
    logger.info('migrate_messages_to_blobdb: batch done, last_pk=%d, failures=%d', last_pk, len(failures))

    migrate_messages_to_blobdb.apply_async(
        kwargs=dict(
            start_after_pk=last_pk,
            batch_size=batch_size,
            start_date=start_date,
            end_date=end_date,
            email_lists=email_lists,
            max_workers=max_workers,
            countdown=countdown,
        ),
        countdown=countdown,
        queue='blobdb',
    )


@shared_task
def rebuild_messages_json(
    start_after_pk=0,
    batch_size=1000,
    start_date=None,
    end_date=None,
    email_lists=None,
    max_workers=50,
    countdown=30,
):
    """Rebuild JSON blobs for one batch of Messages, then self-chain.

    To kick off:   rebuild_messages_json.apply_async(queue='blobdb')
    To stop:       cache.set('rebuild_messages_json_stop', True, timeout=None)
    To resume:     cache.delete('rebuild_messages_json_stop')
                   rebuild_messages_json.apply_async(queue='blobdb', kwargs={'start_after_pk': <last logged pk>, ...})
    """
    from mlarchive.archive.models import Message
    from mlarchive.archive.utils import rebuild_json_blobs

    if cache.get(REBUILD_JSON_STOP_KEY):
        logger.info('rebuild_messages_json: halted by stop flag, resume with start_after_pk=%d', start_after_pk)
        return

    filters = {'pk__gt': start_after_pk}
    if start_date is not None:
        filters['date__gte'] = start_date
    if end_date is not None:
        filters['date__lt'] = end_date
    if email_lists:
        filters['email_list__name__in'] = email_lists

    batch = list(
        Message.objects
        .select_related('email_list')
        .filter(**filters)
        .order_by('pk')[:batch_size]
    )

    if not batch:
        logger.info('rebuild_messages_json: complete, last_pk=%d', start_after_pk)
        return

    failures = rebuild_json_blobs(batch, max_workers=max_workers)
    last_pk = batch[-1].pk
    logger.info('rebuild_messages_json: batch done, last_pk=%d, failures=%d', last_pk, len(failures))

    rebuild_messages_json.apply_async(
        kwargs=dict(
            start_after_pk=last_pk,
            batch_size=batch_size,
            start_date=start_date,
            end_date=end_date,
            email_lists=email_lists,
            max_workers=max_workers,
            countdown=countdown,
        ),
        countdown=countdown,
        queue='blobdb',
    )
