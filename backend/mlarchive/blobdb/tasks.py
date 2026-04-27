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


def _bucket_for_message(message):
    if message.email_list.private:
        return 'ml-messages-private'
    return 'ml-messages'


@shared_task
def migrate_messages_to_blobdb(
    start_after_pk=0,
    batch_size=1000,
    start_date=None,
    end_date=None,
    email_lists=None,
):
    """Copy raw message content from the filesystem into the blobdb.

    Safe to re-run: ignore_conflicts=True respects the (bucket, name) unique constraint.
    To resume after a failure, pass start_after_pk=<last logged pk>.

    Args:
        start_after_pk: skip messages with pk <= this value
        batch_size: number of blobs per bulk_create call
        start_date: only include messages with date >= this value (ISO 8601 string or date object)
        end_date: only include messages with date < this value (ISO 8601 string or date object)
        email_lists: list of email list names to include; None means all lists
    """
    from mlarchive.archive.models import Message
    from mlarchive.blobdb.models import Blob

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
        .iterator(chunk_size=batch_size)
    )

    batch = []
    last_pk = start_after_pk
    total = 0
    errors = 0

    for message in qs:
        try:
            with open(message.get_file_path(), 'rb') as f:
                content = f.read()
        except FileNotFoundError:
            logger.warning('migrate_messages_to_blobdb: missing file for pk=%d path=%s', message.pk, message.get_file_path())
            errors += 1
            last_pk = message.pk
            continue

        batch.append(Blob(
            name=message.get_blob_name(),
            bucket=_bucket_for_message(message),
            content=content,
            content_type='message/rfc822',
        ))
        last_pk = message.pk

        if len(batch) >= batch_size:
            Blob.objects.bulk_create(batch, ignore_conflicts=True)
            total += len(batch)
            logger.info('migrate_messages_to_blobdb: %d blobs written, last_pk=%d, errors=%d', total, last_pk, errors)
            batch = []

    if batch:
        Blob.objects.bulk_create(batch, ignore_conflicts=True)
        total += len(batch)

    logger.info('migrate_messages_to_blobdb: complete. %d blobs written, %d files missing, last_pk=%d', total, errors, last_pk)
