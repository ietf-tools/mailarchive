# Copyright The IETF Trust 2026, All Rights Reserved
"""Recompute Blob checksums that no longer match their content.

Blob.save() once recomputed checksum but, when called with update_fields as
QuerySet.update_or_create() does, never wrote it. Every overwrite through
BlobdbStorage therefore left the previous digest beside the new bytes. That is
routine for ml-messages-json, whose blobs are rewritten whenever a neighbour in the
thread or list arrives. The reconcile takes the checksum column as the truth about
the bytes, so a stale column made it "repair" correct StoredObject rows into wrong
ones. This module puts the column right, see recompute_stale_checksums_task in
archive.tasks; a reconcile with repair then puts the rows right. The R2 copy of an affected blob carries the stale digest as object metadata,
since replication copies the column verbatim, so each fixed blob is also queued for
replication the way a save would queue it.
"""

import json

from django.db import connections

from mlarchive.archive.stored_object_reconciliation import Progress
from mlarchive.blobdb.apps import get_blobdb
from mlarchive.blobdb.models import Blob
from mlarchive.blobdb.replication import replication_enabled
from mlarchive.blobdb.tasks import pybob_the_blob_replicator_task

import logging
logger = logging.getLogger(__name__)


STALE_CHECKSUM = "checksum <> encode(sha384(content), 'hex')"


def recompute_stale_checksums(bucket=None, batch_size=1000, dry_run=False, replicate=True):
    """Set checksum to the digest of content wherever the two disagree.

    Walks the blobs in pk order, batch_size at a time, and runs one UPDATE per page
    that touches only the rows whose stored checksum differs from a digest computed
    inside the database, so no content crosses the wire. Only checksum changes;
    modified is left alone because the bytes did not change. Each fixed blob in a
    replicated bucket is then queued for the replicator task, one task per blob on
    the blobdb queue exactly as a save would, so the R2 copy gets the right sha384
    metadata; pass replicate=False to leave the replica alone. Restricted to bucket
    if given. With dry_run the stale rows are counted instead of updated. Returns a
    dict with the rows examined, the rows fixed (or for a dry run the rows that would
    be) and the replication tasks queued.
    """
    blobs = Blob.objects.all()
    conditions = ['id > %s', 'id <= %s', STALE_CHECKSUM]
    if bucket is not None:
        blobs = blobs.filter(bucket=bucket)
        conditions.append('bucket = %s')
    where = ' AND '.join(conditions)
    if dry_run:
        sql = f'SELECT count(*) FROM blobdb_blob WHERE {where}'
    else:
        sql = (
            f"UPDATE blobdb_blob SET checksum = encode(sha384(content), 'hex') WHERE {where} "
            'RETURNING bucket, name'
        )

    label = f'checksums {bucket or "all buckets"}'
    stats = {'examined': 0, 'stale': 0, 'replicated': 0}
    progress = Progress(label)
    cursor = 0
    with connections[get_blobdb()].cursor() as db:
        while True:
            pks = list(blobs.filter(pk__gt=cursor).order_by('pk').values_list('pk', flat=True)[:batch_size])
            if not pks:
                break
            params = [cursor, pks[-1]] + ([bucket] if bucket is not None else [])
            db.execute(sql, params)
            if dry_run:
                stale = db.fetchone()[0]
            else:
                fixed = db.fetchall()
                stale = len(fixed)
                if replicate:
                    stats['replicated'] += _queue_replication(fixed)
            cursor = pks[-1]
            stats['examined'] += len(pks)
            stats['stale'] += stale
            progress.update(stats['examined'], cursor)
    progress.done(stats['examined'])
    verb = 'would fix' if dry_run else 'fixed'
    logger.info(
        f'recompute_stale_checksums {label}: {stats["examined"]} examined, {verb} {stats["stale"]}, '
        f'{stats["replicated"]} queued for replication')
    return stats


def _queue_replication(blobs):
    """Queue one replicator task per (bucket, name) in a replicated bucket, returning the count.

    The UPDATE that produced the names has already committed, since it ran outside
    any transaction, so the task will see the new checksum when it fetches the row.
    """
    queued = 0
    for bucket, name in blobs:
        if not replication_enabled(bucket):
            continue
        pybob_the_blob_replicator_task.delay(json.dumps({'name': name, 'bucket': bucket}))
        queued += 1
    return queued
