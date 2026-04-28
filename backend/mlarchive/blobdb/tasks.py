# Copyright The IETF Trust 2025, All Rights Reserved

import json
import logging

from celery import shared_task

from .replication import replicate_blob, ReplicationError

logger = logging.getLogger(__name__)


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
):
    """Copy raw message content from the filesystem into blobdb and replicate to R2.

    Safe to re-run: ignore_conflicts=True respects the (bucket, name) unique constraint.
    To resume after a failure, pass start_after_pk=<last logged pk>.

    Args:
        start_after_pk: skip messages with pk <= this value
        batch_size: number of messages per batch
        start_date: only include messages with date >= this value (ISO 8601 string or date object)
        end_date: only include messages with date < this value (ISO 8601 string or date object)
        email_lists: list of email list names to include; None means all lists
        max_workers: thread pool size for R2 replication
    """
    from mlarchive.archive.models import Message
    from mlarchive.archive.utils import migrate_messages_to_blobdb as _migrate_batch

    filters = {'pk__gt': start_after_pk}
    if start_date is not None:
        filters['date__gte'] = start_date
    if end_date is not None:
        filters['date__lt'] = end_date
    if email_lists:
        filters['email_list__name__in'] = email_lists

    qs = (
        Message.objects
        .select_related('email_list')
        .filter(**filters)
        .order_by('pk')
    )

    total = qs.count()
    processed = 0
    last_pk = start_after_pk
    total_failures = []

    for offset in range(0, total, batch_size):
        batch = list(qs[offset:offset + batch_size])
        failures = _migrate_batch(batch, max_workers=max_workers)
        total_failures.extend(failures)
        last_pk = batch[-1].pk
        processed += len(batch)
        logger.info('migrate_messages_to_blobdb: %d/%d done, last_pk=%d, cumulative failures=%d',
                    processed, total, last_pk, len(total_failures))

    logger.info('migrate_messages_to_blobdb: complete. %d/%d processed, %d failures',
                processed, total, len(total_failures))
