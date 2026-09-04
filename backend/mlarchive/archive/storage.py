# Copyright The IETF Trust 2025, All Rights Reserved

import debug  # pyflakes:ignore
import json

from collections import Counter, defaultdict
from contextlib import contextmanager
from storages.backends.s3 import S3Storage

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import storages
from django.db.models.functions import Length
from django.utils import timezone

from mlarchive.archive.models import StoredObject
from mlarchive.blobdb.models import Blob
from mlarchive.blobdb.storage import BlobdbStorage, MetadataFile

import logging
logger = logging.getLogger(__name__)


@contextmanager
def maybe_log_timing(enabled, op, **kwargs):
    """If enabled, log elapsed time and additional data from kwargs

    Emits log even if an exception occurs
    """
    before = timezone.now()
    exception = None
    try:
        yield
    except Exception as err:
        exception = err
        raise
    finally:
        if enabled:
            dt = timezone.now() - before
            logger.info(
                json.dumps(
                    {
                        "log": "S3Storage_timing",
                        "seconds": dt.total_seconds(),
                        "op": op,
                        "exception": "" if exception is None else repr(exception),
                        **kwargs,
                    }
                )
            )


class MetadataS3Storage(S3Storage):
    def get_default_settings(self):
        # add a default for the ietf_log_blob_timing boolean
        return super().get_default_settings() | {"ietf_log_blob_timing": False}

    def _save(self, name, content: File):
        with maybe_log_timing(
            self.ietf_log_blob_timing, "_save", bucket_name=self.bucket_name, name=name
        ):
            return super()._save(name, content)

    def _open(self, name, mode="rb"):
        with maybe_log_timing(
            self.ietf_log_blob_timing,
            "_open",
            bucket_name=self.bucket_name,
            name=name,
            mode=mode,
        ):
            return super()._open(name, mode)

    def delete(self, name):
        with maybe_log_timing(
            self.ietf_log_blob_timing, "delete", bucket_name=self.bucket_name, name=name
        ):
            super().delete(name)

    def _get_write_parameters(self, name, content=None):
        debug.show('f"getting write parameters for {name}"')
        params = super()._get_write_parameters(name, content)
        # If we have a non-empty explicit content type, use it
        content_type = getattr(content, "content_type", "").strip()
        if content_type != "":
            params["ContentType"] = content_type
        if "Metadata" not in params:
            params["Metadata"] = {}
        if hasattr(content, "custom_metadata"):
            params["Metadata"].update(content.custom_metadata)
        return params


class StoredObjectBlobdbStorage(BlobdbStorage):
    """BlobdbStorage that also records object metadata in the StoredObject table.

    The bytes are authoritative; the StoredObject row is an index over them. The two
    live in different databases, so neither write can be made atomic with the other.
    The ordering of every operation here upholds one invariant: a live StoredObject
    row never outlives the bytes it describes. Callers such as purge_incoming treat a
    matching row as proof that content is safely archived, so a row pointing at bytes
    that are gone would let them delete the last remaining copy.

    That invariant makes the two operations asymmetric:

    - Saving writes the bytes first. If recording the metadata then fails, the result
      is a missing index entry, which the reconcile task repairs, so the failure is
      logged and the save still succeeds.
    - Deleting tombstones the metadata first. If that fails the bytes are left alone
      and the exception propagates, because continuing would leave a live row
      describing content that no longer exists.

    The storage also answers the two questions the reconcile needs and the Storage API
    cannot: exists_many() and inventory(). They are the only place the reconcile
    touches the backend, so a storage over a different backend implements those two
    and the reconcile works unchanged.
    """

    def _metadata_for(self, name, content):
        """Return the custom metadata dict for content, or None if it cannot be read.

        Anything written through storage_utils is a MetadataFile and already knows how
        to produce its own digest. A plain Django File does not, so wrap it in one
        rather than duplicating the computation here. Unseekable content cannot be
        digested at all, and under the log-and-continue policy that must not stop the
        bytes from being stored, so failure is reported as None.
        """
        try:
            metadata = getattr(content, 'custom_metadata', None)
            if metadata is None:
                metadata = MetadataFile(file=content).custom_metadata
            return metadata
        except Exception as err:
            logger.error(
                f'Blobstore Error: could not read metadata for {self.bucket_name}:{name}: '
                f'{repr(err)}'
            )
            return None

    def _save_stored_object(self, name, metadata):
        """Create or refresh the StoredObject row describing name."""
        sha384 = metadata['sha384']
        length = int(metadata['len'])
        now = timezone.now()

        record, created = StoredObject.objects.get_or_create(
            store=self.bucket_name,
            name=name,
            defaults=dict(
                sha384=sha384,
                len=length,
                store_created=now,
                created=now,
                modified=now,
            ),
        )
        if created:
            return record

        # An existing row is refreshed only when the object actually changed, so that
        # re-storing identical content leaves modified alone. A tombstoned row always
        # counts as changed: the object is back.
        unchanged = (
            record.sha384 == sha384
            and record.len == length
            and record.deleted is None
        )
        if unchanged:
            return record

        record.sha384 = sha384
        record.len = length
        record.modified = now
        record.deleted = None
        record.save()
        return record

    def _delete_stored_object(self, name):
        """Tombstone the StoredObject row for name, returning the number updated.

        Zero is not an error. Until the backfill has run most objects predate this
        table, and detecting that drift is the reconcile task's job, not this one's.
        """
        return (
            StoredObject.objects
            .filter(store=self.bucket_name, name=name)
            .exclude_deleted()
            .update(deleted=timezone.now())
        )

    def _save(self, name, content):
        # Digest the content before the save consumes it, while the file position is
        # still known good. MetadataFile caches its result, so a caller that already
        # computed the metadata does not pay for it twice.
        metadata = self._metadata_for(name, content)
        saved_name = super()._save(name, content)
        if metadata is None:
            return saved_name
        try:
            self._save_stored_object(saved_name, metadata)
        except Exception as err:
            logger.error(
                f'Blobstore Error: stored {self.bucket_name}:{saved_name} but failed to '
                f'record its StoredObject: {repr(err)}'
            )
        return saved_name

    def delete(self, name):
        self._delete_stored_object(name)
        super().delete(name)

    def exists_many(self, names):
        """Return the subset of names that have bytes in this store.

        One query per call, where Storage.exists() would be one per name.
        """
        return set(
            self.get_queryset().filter(name__in=list(names)).values_list('name', flat=True))

    def inventory(self, after=None, limit=5000):
        """Return one page of the store's contents and a cursor for the next page.

        The page is a list of (name, sha384, len, modified) tuples describing objects,
        with no byte reads: the digest is the Blob's stored checksum and the length is
        computed in the database. The cursor is opaque; pass it back as after to
        continue. An empty page means the store is exhausted.
        """
        rows = list(
            self.get_queryset()
            .filter(pk__gt=after or 0)
            .order_by('pk')
            .annotate(object_size=Length('content'))
            .values_list('pk', 'name', 'checksum', 'object_size', 'modified')
            [:limit]
        )
        if not rows:
            return [], None
        return [row[1:] for row in rows], rows[-1][0]


def backfill_stored_objects(start_after_pk=0, batch_size=5000):
    """Index one batch of pre-existing blobs as StoredObject rows"""

    rows = list(
        Blob.objects
        .filter(pk__gt=start_after_pk, bucket__in=settings.ARTIFACT_STORAGE_NAMES)
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


# --------------------------------------------------
# Reconcile
# --------------------------------------------------

RECONCILE_SAMPLE_LIMIT = 20
# Above this many live rows without bytes in one bucket, repair leaves them alone.
# A few are worth tombstoning automatically; thousands mean something is destroying
# bytes, and tombstoning them all would erase the evidence of the scale.
RECONCILE_MAX_MISSING_REPAIRS = 100


class DriftReport:
    """Count drift per category and keep the first few names of each for the log.

    A run over an unindexed bucket can find millions of untracked objects, so the
    names are sampled rather than logged one per line.
    """

    def __init__(self, label, sample_limit=None):
        self.label = label
        self.sample_limit = RECONCILE_SAMPLE_LIMIT if sample_limit is None else sample_limit
        self.counts = Counter()
        self.samples = defaultdict(list)

    def add(self, category, names):
        self.counts[category] += len(names)
        room = self.sample_limit - len(self.samples[category])
        if room > 0:
            self.samples[category].extend(names[:room])

    def log(self):
        for category, count in sorted(self.counts.items()):
            if count == 0:
                continue
            shown = ', '.join(self.samples[category])
            more = count - len(self.samples[category])
            suffix = f' ... and {more} more' if more else ''
            logger.warning(f'reconcile {self.label}: {count} {category}: {shown}{suffix}')


def _reconcile_rows(storage, repair, batch_size, max_missing_repairs, stats):
    """Check that every live StoredObject row for storage still has bytes behind it.

    A live row without bytes is the one state the storage class is built to prevent,
    because readers take a row as proof the object is safely stored. The save path
    cannot produce it, since bytes are written before the row, so it means bytes have
    vanished after the fact: lost data, not a stale index. It is therefore logged at
    ERROR with every name, not sampled like the other categories.

    The repair is to tombstone the row, which protects any other copy a reader might
    otherwise delete on the strength of it. But only up to max_missing_repairs per
    bucket: beyond that the rows are left live and reported, so that a person sees the
    scale of the loss before the evidence of it is tombstoned away.
    """
    bucket = storage.bucket_name
    missing = []
    cursor = 0
    while True:
        rows = list(
            StoredObject.objects
            .filter(store=bucket, pk__gt=cursor)
            .exclude_deleted()
            .order_by('pk')
            .values_list('pk', 'name')
            [:batch_size]
        )
        if not rows:
            break
        cursor = rows[-1][0]
        stats['rows'] += len(rows)

        present = storage.exists_many(name for _, name in rows)
        batch_missing = [(pk, name) for pk, name in rows if name not in present]
        stats['missing'] += len(batch_missing)
        # keep one more than the limit, enough to prove it was exceeded
        room = max_missing_repairs + 1 - len(missing)
        if room > 0:
            missing.extend(batch_missing[:room])

    if not stats['missing']:
        return
    names = ', '.join(name for _, name in missing)
    more = stats['missing'] - len(missing)
    suffix = f' ... and {more} more' if more else ''
    logger.error(f'reconcile {bucket}: {stats["missing"]} live rows with no bytes: {names}{suffix}')
    if not repair:
        return
    if stats['missing'] > max_missing_repairs:
        logger.error(
            f'reconcile {bucket}: {stats["missing"]} live rows with no bytes exceeds '
            f'max_missing_repairs={max_missing_repairs}; left live for investigation')
        return
    pks = [pk for pk, _ in missing]
    for start in range(0, len(pks), 1000):
        # exclude_deleted again: a delete that tombstoned the row since we read it
        # must not be counted as our repair
        stats['repaired'] += (
            StoredObject.objects
            .filter(pk__in=pks[start:start + 1000])
            .exclude_deleted()
            .update(deleted=timezone.now())
        )


def _reconcile_objects(storage, repair, batch_size, stats, drift):
    """Check that every object in storage has a live, accurate StoredObject row.

    Drift found here comes from the bytes-first write window, when the bytes land but
    recording the row fails, and from any write that bypasses the storage. Three
    states are repaired from the storage's own inventory, exactly as the backfill
    does: no row at all, a live row whose digest or length differ, and a tombstoned
    row whose bytes were written after the tombstone.

    A tombstoned row whose bytes are *older* than the tombstone is reported but left
    alone. That is either a delete caught between tombstoning the row and removing
    the bytes, which will resolve itself, or bytes a failed delete left behind.
    Reviving the row in the first case would leave a live row pointing at bytes
    about to vanish, the exact state _reconcile_rows exists to remove.
    """
    bucket = storage.bucket_name
    cursor = None
    while True:
        objects, cursor = storage.inventory(after=cursor, limit=batch_size)
        if not objects:
            return
        stats['objects'] += len(objects)

        records = {
            record.name: record
            for record in StoredObject.objects.filter(
                store=bucket, name__in=[name for name, *_ in objects])
        }
        to_create = []
        to_update = []
        found = defaultdict(list)
        for name, checksum, object_size, modified in objects:
            record = records.get(name)
            if record is None:
                found['untracked'].append(name)
                to_create.append(StoredObject(
                    store=bucket,
                    name=name,
                    sha384=checksum,
                    len=object_size,
                    store_created=modified,
                    created=modified,
                    modified=modified,
                ))
                continue
            if record.deleted is not None:
                if modified <= record.deleted:
                    found['lingering'].append(name)
                    continue
                found['tombstoned'].append(name)
            elif record.sha384 != checksum or record.len != object_size:
                found['mismatched'].append(name)
            else:
                continue
            record.sha384 = checksum
            record.len = object_size
            record.modified = max(modified, record.modified)
            record.deleted = None
            to_update.append(record)

        labels = {
            'untracked': 'objects with no row',
            'tombstoned': 'tombstoned rows whose bytes were rewritten',
            'lingering': 'tombstoned rows whose bytes remain',
            'mismatched': 'rows whose digest or length differ',
        }
        for category, names in found.items():
            stats[category] += len(names)
            drift.add(labels[category], names)

        if repair:
            # ignore_conflicts covers a row the storage created between our read and
            # this insert
            StoredObject.objects.bulk_create(to_create, batch_size=1000, ignore_conflicts=True)
            StoredObject.objects.bulk_update(
                to_update, ['sha384', 'len', 'modified', 'deleted'], batch_size=1000)
            stats['repaired'] += len(to_create) + len(to_update)


def reconcile_bucket(bucket, repair=False, batch_size=5000,
                     max_missing_repairs=RECONCILE_MAX_MISSING_REPAIRS):
    """Diff the StoredObject rows for bucket against its blobs, repairing on request.

    The bytes are authoritative and the rows are an index over them, so every repair
    moves a row towards the bytes and never the other way. Two passes, each walking
    its side by pk in batches of batch_size: rows that have lost their bytes, then
    blobs whose row is absent, stale or wrongly tombstoned. See the pass functions
    for what each state means and how it is repaired.

    Live rows without bytes are the exception to routine repair. They mean bytes were
    lost, so they are logged at ERROR in full, and if more than max_missing_repairs
    are found in the bucket they are left untouched for a person to look at.

    Returns a dict of counts: the rows and objects examined, one entry per drift
    category (missing, untracked, tombstoned, lingering, mismatched) and the number
    of rows repaired. Other drift is logged with a sample of the names involved.

    The passes know nothing about the backend. Everything they need from it comes
    through the storage's exists_many() and inventory() methods.
    """
    if bucket not in settings.ARTIFACT_STORAGE_NAMES:
        raise ValueError(f'{bucket} is not an artifact storage')
    storage = storages[bucket]
    stats = Counter(
        rows=0, objects=0, missing=0, untracked=0, tombstoned=0, lingering=0,
        mismatched=0, repaired=0)
    drift = DriftReport(bucket)
    _reconcile_rows(storage, repair, batch_size, max_missing_repairs, stats)
    _reconcile_objects(storage, repair, batch_size, stats, drift)
    drift.log()
    logger.info(f'reconcile {bucket}: {dict(stats)}')
    return dict(stats)
