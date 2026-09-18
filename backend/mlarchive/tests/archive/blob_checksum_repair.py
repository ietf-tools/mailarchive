# Copyright The IETF Trust 2026, All Rights Reserved
import json
import logging
from hashlib import sha384
from unittest.mock import patch

import pytest

from django.core.files.storage import storages
from django.db import models

from mlarchive.archive.blob_checksum_repair import recompute_stale_checksums
from mlarchive.archive.stored_object_reconciliation import reconcile_bucket
from mlarchive.archive.models import StoredObject
from mlarchive.archive.tasks import recompute_stale_checksums_task
from mlarchive.blobdb.models import Blob
from mlarchive.blobdb.storage import BlobFile


BUCKET = 'ml-messages-json'
CONTENT = b'{"body": "These are my bytes."}'


def digest(content):
    return sha384(content).hexdigest()


def overwrite_leaving_checksum_stale(bucket, name, content):
    """Rewrite content the way Blob.save() did before it wrote checksum on overwrite."""
    blob = Blob.objects.get(bucket=bucket, name=name)
    blob.content = content
    models.Model.save(blob, update_fields=['content'])
    return blob


@pytest.fixture
def replicator():
    """Capture replicator tasks for every bucket instead of sending them to the broker."""
    with patch('mlarchive.archive.blob_checksum_repair.replication_enabled', return_value=True), \
            patch('mlarchive.archive.blob_checksum_repair.pybob_the_blob_replicator_task') as task:
        yield task


def queued(replicator):
    return [json.loads(call.args[0]) for call in replicator.delay.call_args_list]


@pytest.mark.django_db
def test_recompute_fixes_only_stale_checksums(replicator):
    storage = storages[BUCKET]
    storage.save('acme/stale', BlobFile(content=CONTENT))
    storage.save('acme/fresh', BlobFile(content=CONTENT))
    changed = b'{"body": "rewritten"}'
    overwrite_leaving_checksum_stale(BUCKET, 'acme/stale', changed)
    fresh_before = Blob.objects.get(bucket=BUCKET, name='acme/fresh')
    stale_before = Blob.objects.get(bucket=BUCKET, name='acme/stale')
    assert stale_before.checksum == digest(CONTENT)

    assert recompute_stale_checksums(bucket=BUCKET) == {'examined': 2, 'stale': 1, 'replicated': 1}
    assert queued(replicator) == [{'name': 'acme/stale', 'bucket': BUCKET}]

    stale = Blob.objects.get(bucket=BUCKET, name='acme/stale')
    assert stale.checksum == digest(changed)
    assert stale.modified == stale_before.modified
    fresh = Blob.objects.get(bucket=BUCKET, name='acme/fresh')
    assert fresh.checksum == fresh_before.checksum == digest(CONTENT)
    assert fresh.modified == fresh_before.modified


@pytest.mark.django_db
def test_recompute_dry_run_changes_nothing(replicator):
    storages[BUCKET].save('acme/stale', BlobFile(content=CONTENT))
    overwrite_leaving_checksum_stale(BUCKET, 'acme/stale', b'{"body": "rewritten"}')

    assert recompute_stale_checksums(bucket=BUCKET, dry_run=True) == {'examined': 1, 'stale': 1, 'replicated': 0}
    assert Blob.objects.get(bucket=BUCKET, name='acme/stale').checksum == digest(CONTENT)
    assert queued(replicator) == []


@pytest.mark.django_db
def test_recompute_respects_bucket_and_batches(replicator):
    for bucket in ('ml-messages', BUCKET):
        storage = storages[bucket]
        for i in range(3):
            storage.save(f'acme/{i}', BlobFile(content=CONTENT))
            overwrite_leaving_checksum_stale(bucket, f'acme/{i}', b'{"body": "%d"}' % i)

    assert recompute_stale_checksums(bucket=BUCKET, batch_size=2) == {'examined': 3, 'stale': 3, 'replicated': 3}
    for i in range(3):
        assert Blob.objects.get(bucket=BUCKET, name=f'acme/{i}').checksum == digest(b'{"body": "%d"}' % i)
        assert Blob.objects.get(bucket='ml-messages', name=f'acme/{i}').checksum == digest(CONTENT)

    assert recompute_stale_checksums(batch_size=2) == {'examined': 6, 'stale': 3, 'replicated': 3}
    assert recompute_stale_checksums() == {'examined': 6, 'stale': 0, 'replicated': 0}
    assert sorted(b['bucket'] for b in queued(replicator)) == ['ml-messages'] * 3 + [BUCKET] * 3


@pytest.mark.django_db
def test_recompute_then_reconcile_restores_rows(replicator):
    """The production recovery: fix the checksum column, then let the reconcile fix the rows.

    A reconcile run against stale checksums copies them into the StoredObject rows.
    Recomputing the column and reconciling again must bring every row back to the
    digest of the bytes.
    """
    storage = storages[BUCKET]
    storage.save('acme/one', BlobFile(content=CONTENT))
    changed = b'{"body": "rewritten"}'
    overwrite_leaving_checksum_stale(BUCKET, 'acme/one', changed)
    reconcile_bucket(BUCKET, repair=True)
    assert StoredObject.objects.get(store=BUCKET, name='acme/one').sha384 == digest(CONTENT)

    recompute_stale_checksums(bucket=BUCKET)
    stats = reconcile_bucket(BUCKET, repair=True)
    assert stats['mismatched'] == stats['repaired'] == 1
    assert StoredObject.objects.get(store=BUCKET, name='acme/one').sha384 == digest(changed)
    assert reconcile_bucket(BUCKET)['mismatched'] == 0


@pytest.mark.django_db
def test_recompute_skips_replication_when_disabled_or_declined(replicator):
    for name in ('acme/one', 'acme/two'):
        storages[BUCKET].save(name, BlobFile(content=CONTENT))
        overwrite_leaving_checksum_stale(BUCKET, name, b'{"body": "rewritten"}')

    with patch('mlarchive.archive.blob_checksum_repair.replication_enabled', return_value=False):
        stats = recompute_stale_checksums(bucket=BUCKET, batch_size=1)
    assert stats == {'examined': 2, 'stale': 2, 'replicated': 0}
    assert queued(replicator) == []

    for name in ('acme/one', 'acme/two'):
        overwrite_leaving_checksum_stale(BUCKET, name, b'{"body": "rewritten again"}')
    assert recompute_stale_checksums(bucket=BUCKET, replicate=False) == {'examined': 2, 'stale': 2, 'replicated': 0}
    assert queued(replicator) == []


@pytest.mark.django_db
def test_recompute_task_forwards_every_parameter():
    with patch('mlarchive.archive.tasks.recompute_stale_checksums') as recompute:
        recompute_stale_checksums_task(bucket=BUCKET, batch_size=7, dry_run=True, replicate=False)

    recompute.assert_called_once_with(bucket=BUCKET, batch_size=7, dry_run=True, replicate=False)


@pytest.mark.django_db
def test_recompute_task_defaults_and_logs_errors(caplog):
    caplog.set_level(logging.ERROR)
    with patch('mlarchive.archive.tasks.recompute_stale_checksums',
               side_effect=RuntimeError('boom')) as recompute:
        recompute_stale_checksums_task()

    recompute.assert_called_once_with(bucket=None, batch_size=1000, dry_run=False, replicate=True)
    assert 'Error in recompute_stale_checksums_task: boom' in caplog.text


@pytest.mark.django_db
def test_recompute_task_end_to_end(replicator):
    """The task fixes the column and queues replication like a direct call."""
    storages[BUCKET].save('acme/stale', BlobFile(content=CONTENT))
    overwrite_leaving_checksum_stale(BUCKET, 'acme/stale', b'{"body": "rewritten"}')

    recompute_stale_checksums_task(bucket=BUCKET, dry_run=True)
    assert Blob.objects.get(bucket=BUCKET, name='acme/stale').checksum == digest(CONTENT)
    assert queued(replicator) == []

    recompute_stale_checksums_task(bucket=BUCKET)
    assert Blob.objects.get(bucket=BUCKET, name='acme/stale').checksum == digest(b'{"body": "rewritten"}')
    assert queued(replicator) == [{'name': 'acme/stale', 'bucket': BUCKET}]
