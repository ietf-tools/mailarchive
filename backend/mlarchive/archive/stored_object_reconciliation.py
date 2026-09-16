# Copyright The IETF Trust 2026, All Rights Reserved
"""Reconcile the StoredObject index against the bytes in blob storage.

The bytes are authoritative and the StoredObject rows are an index over them. The
functions here diff one against the other, bucket by bucket, and on request move the
rows towards the bytes. The bucket passes know nothing about the storage backend:
everything they need comes through the storage's exists_many() and inventory()
methods. A final pass audits each list's messages against the objects under its
prefix, reporting only.
"""

import time
from collections import Counter, defaultdict

from django.conf import settings
from django.core.files.storage import storages
from django.utils import timezone

from mlarchive.archive.models import EmailList, Message, StoredObject
from mlarchive.archive.storage_utils import list_names

import logging
logger = logging.getLogger(__name__)


RECONCILE_SAMPLE_LIMIT = 20
# Above this many live rows without bytes in one bucket, repair leaves them alone.
# A few are worth tombstoning automatically; thousands mean something is destroying
# bytes, and tombstoning them all would erase the evidence of the scale.
RECONCILE_MAX_MISSING_REPAIRS = 100
# Seconds between progress lines for one pass. Throttling by time rather than by row
# count keeps the volume proportional to how long the run takes, not how big it is.
RECONCILE_PROGRESS_INTERVAL = 60


class Progress:
    """Log a running count for one pass, at most once every interval seconds.

    A pass over a large bucket takes minutes and says nothing until its summary, so
    this reports how many items it has covered, its rate, and the cursor it has
    reached. Since the passes walk in name order and names are list/hashcode, the
    cursor shows which list the pass is in. A pass that finishes inside one interval
    logs only its done() line.
    """

    def __init__(self, label, interval=None):
        self.label = label
        self.interval = RECONCILE_PROGRESS_INTERVAL if interval is None else interval
        self.started = self.last = time.monotonic()

    def update(self, count, cursor):
        now = time.monotonic()
        if now - self.last < self.interval:
            return
        self.last = now
        rate = count / (now - self.started) if now > self.started else 0
        logger.info(f'reconcile {self.label}: {count} so far, {rate:.0f}/s, at {cursor}')

    def done(self, count):
        elapsed = time.monotonic() - self.started
        logger.info(f'reconcile {self.label}: {count} in {elapsed:.0f}s')


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
    # Page by name rather than pk: (store, name) is the unique index, so each page is a
    # bounded range scan instead of a walk of the whole pk index filtered by store.
    cursor = ''
    progress = Progress(f'{bucket} rows')
    while True:
        rows = list(
            StoredObject.objects
            .filter(store=bucket, name__gt=cursor)
            .exclude_deleted()
            .order_by('name')
            .values_list('pk', 'name')
            [:batch_size]
        )
        if not rows:
            break
        cursor = rows[-1][1]
        stats['rows'] += len(rows)

        present = storage.exists_many(name for _, name in rows)
        batch_missing = [(pk, name) for pk, name in rows if name not in present]
        stats['missing'] += len(batch_missing)
        # keep one more than the limit, enough to prove it was exceeded
        room = max_missing_repairs + 1 - len(missing)
        if room > 0:
            missing.extend(batch_missing[:room])
        progress.update(stats['rows'], cursor)
    progress.done(stats['rows'])

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

    Drift found here comes from writes that bypass the storage, chiefly the bulk
    paths (bulk_create, bulk_update) that rebuild_json_blobs and the migration tasks
    use, and from the bytes-first write window when recording the row fails. Three
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
    progress = Progress(f'{bucket} objects')
    while True:
        objects, cursor = storage.inventory(after=cursor, limit=batch_size)
        if not objects:
            progress.done(stats['objects'])
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
            record.modified = modified
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
        progress.update(stats['objects'], cursor)


def reconcile_bucket(bucket, repair=False, batch_size=5000,
                     max_missing_repairs=RECONCILE_MAX_MISSING_REPAIRS):
    """Diff the StoredObject rows for bucket against its blobs, repairing on request.

    The bytes are authoritative and the rows are an index over them, so every repair
    moves a row towards the bytes and never the other way. Two passes, each walking
    its side in name order in batches of batch_size: rows that have lost their bytes, then
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


def audit_list_objects(elist):
    """Compare the messages of elist with the live stored objects under its prefix.

    Every Message should have an object named after it in the list's bucket, and every
    object there should belong to a Message. Returns two sets of hashcodes, as they
    appear in object names (padding stripped): those with a message but no object,
    and those with an object but no message. Either being non-empty is logged with a
    sample of the hashcodes. Nothing is repaired: a message without bytes cannot be
    reconstructed here, and an object without a message is for a person to judge.
    """
    prefix = f'{elist.name}/'
    object_hashes = {
        name[len(prefix):] for name in list_names(elist.blob_bucket, prefix=prefix)}
    message_hashes = {
        hashcode.rstrip('=')
        for hashcode in Message.objects.filter(email_list=elist)
        .values_list('hashcode', flat=True).iterator(chunk_size=5000)
    }
    only_messages = message_hashes - object_hashes
    only_objects = object_hashes - message_hashes
    if only_messages or only_objects:
        drift = DriftReport(f'list {elist.name}')
        drift.add('messages with no stored object', sorted(only_messages))
        drift.add('stored objects with no message', sorted(only_objects))
        drift.log()
    return only_messages, only_objects


def reconcile_stored_objects(bucket=None, repair=False, batch_size=5000,
                             max_missing_repairs=RECONCILE_MAX_MISSING_REPAIRS):
    """Check the StoredObject index against blob storage and the message table.

    First each artifact storage, or just bucket if given, is diffed against its blobs
    by reconcile_bucket, which repairs the index when repair is set, except that live
    rows without bytes are repaired only up to max_missing_repairs per bucket, since
    they mean bytes were lost (see reconcile_bucket). Then every list
    whose messages live in one of those buckets is audited by audit_list_objects,
    which only reports. The order matters: the list audit reads the index, so it is
    trustworthy only once the index agrees with the bytes.

    Returns a dict of counts: the per-bucket counts summed across buckets (see
    reconcile_bucket), plus the lists audited, how many of them showed a mismatch,
    and the total hashcodes found on only one side.
    """
    buckets = list(settings.ARTIFACT_STORAGE_NAMES)
    if bucket is not None:
        if bucket not in buckets:
            raise ValueError(f'{bucket} is not an artifact storage')
        buckets = [bucket]

    logger.info(
        f'reconcile_stored_objects: starting, repair={repair}, buckets={", ".join(buckets)}')
    stats = Counter()
    for name in buckets:
        stats.update(reconcile_bucket(
            name, repair=repair, batch_size=batch_size,
            max_missing_repairs=max_missing_repairs))

    stats.update(lists=0, list_mismatches=0, only_messages=0, only_objects=0)
    progress = Progress('lists')
    for elist in EmailList.objects.order_by('name'):
        if elist.blob_bucket not in buckets:
            continue
        only_messages, only_objects = audit_list_objects(elist)
        stats['lists'] += 1
        if only_messages or only_objects:
            stats['list_mismatches'] += 1
        stats['only_messages'] += len(only_messages)
        stats['only_objects'] += len(only_objects)
        progress.update(stats['lists'], elist.name)
    progress.done(stats['lists'])

    logger.info(f'reconcile_stored_objects: {dict(stats)}')
    return dict(stats)
