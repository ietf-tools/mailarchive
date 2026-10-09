# Copyright The IETF Trust 2026, All Rights Reserved

"""Derived artifacts: the objects built from the database and served from the edge.

A derived artifact is anything built from Message and EmailList rows and
served without going through Django: the message JSON blobs the messages
worker reads today, and later the navigation and month indexes. Each one is
named by an ArtifactRef(kind, key).

Callers describe what happened with an event (MessageAdded, MessageRemoved,
...) and pass it to emit(). emit() computes the set of refs the event may
have changed with touched_refs(), while the database still shows the state
the event describes, and arranges for those refs to be applied once the
transaction commits.

apply() rebuilds each ref from the database as it is at that point: if the
source exists and is public, the object is written, otherwise it is deleted.
Overwriting the object is the invalidation. Because apply() looks at the
current state, a ref that is applied twice, applied after a retry, or applied
when nothing actually changed does no harm. Including too many refs is safe;
leaving one out is the only failure, and reconciliation is there to catch it.

    derived.emit(derived.MessageAdded(message.pk))

    with derived.batch():
        for message in messages:
            message.delete()      # pre_delete emits MessageRemoved

Refs are applied once the 'default' database commits, so changes rolled back
never reach storage. A Celery task applies them and retries the ones that fail.
"""

import contextlib
import contextvars
import dataclasses
import datetime
import logging
import requests
import sys
import traceback

from cloudflare import Cloudflare, APIError
from django.conf import settings
from django.db import transaction
from django.urls import reverse

from mlarchive.archive.message_json import store_message_json
from mlarchive.archive.models import EmailList, Message, Thread, is_small_year
from mlarchive.archive.storage_utils import remove_from_storage

logger = logging.getLogger(__name__)

# refs per apply_derived_artifacts_task call
TASK_CHUNK_SIZE = 500

# Cloudflare allows up to 30 tags or urls in one purge call, see
# https://developers.cloudflare.com/cache/how-to/purge-cache/#availability-and-limits
PURGE_CHUNK_SIZE = 30


# --------------------------------------------------
# Artifact kinds and builders
# --------------------------------------------------

MESSAGE_JSON = 'message_json'   # key: "<list name>/<hashcode>"
THREAD = 'thread'               # key: "<thread id>"
MONTH_INDEX = 'month_index'     # key: "<list name>/<YYYY-MM>"

# kind -> builder(key), or None for a kind with no object of its own yet.
# THREAD and MONTH_INDEX pages are still rendered by Django; they are tracked
# so legacy_purge() can turn them into Cloudflare purges.
_BUILDERS = {
    THREAD: None,
    MONTH_INDEX: None,
}


def builder(kind):
    """Register the decorated function as the builder for kind"""
    def register(func):
        _BUILDERS[kind] = func
        return func
    return register


@dataclasses.dataclass(frozen=True, order=True)
class ArtifactRef:
    kind: str
    key: str

    def __post_init__(self):
        if self.kind not in _BUILDERS:
            raise ValueError(f'Unknown derived artifact kind: {self.kind}')

    def __str__(self):
        return f'{self.kind}:{self.key}'


def message_json_ref(list_name, hashcode):
    return ArtifactRef(MESSAGE_JSON, f'{list_name}/{hashcode}')


def thread_ref(thread_id):
    return ArtifactRef(THREAD, str(thread_id))


def month_index_ref(list_name, date):
    return ArtifactRef(MONTH_INDEX, f'{list_name}/{date.year:04d}-{date.month:02d}')


@builder(MESSAGE_JSON)
def build_message_json(key):
    """Write the message's ml-messages-json blob, or delete it if the message
    is gone or its list is private.
    """
    list_name, hashcode = key.split('/', 1)
    message = Message.objects.filter(
        email_list__name=list_name,
        hashcode=hashcode).select_related('email_list', 'thread').first()
    if message and not message.email_list.private:
        store_message_json(message)
    else:
        # same name Message.get_blob_name() gives
        remove_from_storage(kind='ml-messages-json', name=key.rstrip('='), warn_if_missing=False)


# --------------------------------------------------
# Dependency knowledge
# --------------------------------------------------

def _message_artifacts(list_name, hashcode, thread_id, date, thread_date):
    return {
        message_json_ref(list_name, hashcode),
        thread_ref(thread_id),
        month_index_ref(list_name, date),
        month_index_ref(list_name, thread_date),
    }


def artifacts_for_message(message):
    """Returns the refs built from this message: its JSON blob, its thread,
    the month index of its date and the month index its thread is listed
    under (the month of the thread's first message).
    """
    return _message_artifacts(
        message.email_list.name,
        message.hashcode,
        message.thread_id,
        message.date,
        message.thread.date)


def artifacts_for_list(email_list):
    """Returns the refs built from every message in the list"""
    refs = set()
    rows = Message.objects.filter(email_list=email_list).values_list(
        'hashcode', 'thread_id', 'date', 'thread__date')
    for hashcode, thread_id, date, thread_date in rows.iterator():
        refs |= _message_artifacts(email_list.name, hashcode, thread_id, date, thread_date)
    return refs


def global_artifacts():
    """Returns the refs that don't belong to any one list. None exist yet;
    the lists index and sitemap will go here.
    """
    return set()


def _dependent_messages(message):
    """Returns the messages whose derived artifacts show this message.

    These are every message in its thread (navigation links, thread snippet),
    the messages before and after it in list order (next/previous in list),
    the last message of the previous thread and the first message of the
    next thread (next/previous in thread cross thread boundaries, see
    Message.next_in_thread()).
    """
    thread = message.thread
    messages = list(thread.message_set.select_related('email_list', 'thread'))
    threads = Thread.objects.filter(email_list=message.email_list)
    previous_thread = threads.filter(date__lt=thread.date).order_by('date').last()
    next_thread = threads.filter(date__gt=thread.date).order_by('date').first()
    neighbors = [message.previous_in_list(), message.next_in_list()]
    if previous_thread:
        neighbors.append(previous_thread.message_set.order_by('thread_order').last())
    if next_thread:
        neighbors.append(next_thread.message_set.order_by('thread_order').first())
    messages.extend(neighbor for neighbor in neighbors if neighbor)
    return messages


def _refs_for_message_change(message_id):
    message = Message.objects.select_related('email_list', 'thread').get(pk=message_id)
    refs = artifacts_for_message(message)
    for other in _dependent_messages(message):
        refs |= artifacts_for_message(other)
    return refs


# --------------------------------------------------
# Events
# --------------------------------------------------

@dataclasses.dataclass(frozen=True)
class MessageAdded:
    """A message is fully archived: saved, threaded, attachments created"""
    message_id: int


@dataclasses.dataclass(frozen=True)
class MessageRemoved:
    """A message is about to be deleted. Emit while the row still exists"""
    message_id: int


@dataclasses.dataclass(frozen=True)
class MessageRestored:
    """A removed message is returned to the archive (#4110)"""
    message_id: int


@dataclasses.dataclass(frozen=True)
class MessageMoved:
    """A message moved from the list source_list_id to its current list"""
    message_id: int
    source_list_id: int


@dataclasses.dataclass(frozen=True)
class ListVisibilityChanged:
    """A list's private flag changed. Its current value is in the database"""
    list_id: int


@dataclasses.dataclass(frozen=True)
class ListChanged:
    """A list's metadata (name, description, active) changed"""
    list_id: int


@dataclasses.dataclass(frozen=True)
class Rebuild:
    """Rebuild every artifact of one list"""
    list_id: int


def touched_refs(event):
    """Returns the set of ArtifactRefs the event may have changed.

    Raises NotImplementedError for an event type with no case here.
    """
    match event:
        case MessageAdded(message_id=pk) | MessageRemoved(message_id=pk):
            return _refs_for_message_change(pk)
        case ListVisibilityChanged(list_id=pk) | Rebuild(list_id=pk):
            return artifacts_for_list(EmailList.objects.get(pk=pk))
        case _:
            raise NotImplementedError(
                f'touched_refs() is not implemented for {type(event).__name__}')


# --------------------------------------------------
# Delivery
# --------------------------------------------------

_current_batch = contextvars.ContextVar('derived_batch', default=None)


def emit(event):
    """Compute the refs the event touched and apply them on commit.

    Inside batch(), the refs are added to the batch instead.
    """
    refs = touched_refs(event)
    pending = _current_batch.get()
    if pending is not None:
        pending |= refs
        return
    _flush_on_commit(refs)


@contextlib.contextmanager
def batch():
    """Collect the refs of every event emitted inside the block and apply
    their union once, on commit.

    The flush is registered even if the block raises: in autocommit the work
    done before the exception is already committed. Inside a transaction that
    then rolls back, Django drops the flush with it. A nested batch() joins
    the outer one.
    """
    if _current_batch.get() is not None:
        yield
        return
    pending = set()
    token = _current_batch.set(pending)
    try:
        yield
    finally:
        _current_batch.reset(token)
        if pending:
            _flush_on_commit(pending)


def _flush_on_commit(refs):
    """Run _flush(refs) once the default database commits.

    robust: by then the change itself is committed, so a failure here, such
    as the broker being down, is logged rather than raised to the code that
    made the change. Reconciliation repairs the refs it lost.
    """
    # a closure, not functools.partial: Django logs a failing robust
    # callback's __qualname__, which partial objects lack
    def flush():
        _flush(refs)
    transaction.on_commit(flush, using='default', robust=True)


def _flush(refs):
    if not settings.DERIVED_ARTIFACTS_ASYNC:
        apply_and_purge(refs)
        return
    from mlarchive.archive.tasks import apply_derived_artifacts_task
    ordered = sorted(refs)
    for i in range(0, len(ordered), TASK_CHUNK_SIZE):
        apply_derived_artifacts_task.delay(serialize_refs(ordered[i:i + TASK_CHUNK_SIZE]))


def serialize_refs(refs):
    return [[ref.kind, ref.key] for ref in refs]


def deserialize_refs(data):
    return {ArtifactRef(kind, key) for kind, key in data}


def apply(refs):
    """Rebuild or delete each ref's object from the current database state.

    A failure does not stop the rest. Returns the list of (ref, exception)
    failures.
    """
    failures = []
    for ref in sorted(refs):
        build = _BUILDERS[ref.kind]
        if build is None:
            continue
        try:
            build(ref.key)
        except Exception as err:
            logger.error(f'Failed to apply derived artifact {ref}: {repr(err)}')
            failures.append((ref, err))
    return failures


def apply_and_purge(refs):
    """apply() the refs, then purge the cached pages built from them.
    Returns apply()'s failures.
    """
    failures = apply(refs)
    legacy_purge(refs)
    return failures


# --------------------------------------------------
# Legacy Cloudflare purging
# --------------------------------------------------
# Temporary, while message pages and static index pages are still rendered
# by Django and cached by Cloudflare. Remove once they are served from
# objects written by apply().

def legacy_purge_targets(refs):
    """Returns (tags, urls), the Cloudflare Cache-Tags and urls of the cached
    pages built from refs.

    Message pages are tagged by thread (Message.get_cache_tag()), so a THREAD
    ref purges every message page in the thread. A MONTH_INDEX ref purges that
    list-month's static date and thread index pages. MESSAGE_JSON refs need
    nothing of their own: their pages go with their thread's tag.
    """
    tags = set()
    urls = set()
    small_years = {}
    lists = {}
    this_year = datetime.datetime.today().year
    for ref in refs:
        if ref.kind == THREAD:
            tags.add(f'thread-{ref.key}')
        elif ref.kind == MONTH_INDEX:
            list_name, year_month = ref.key.split('/', 1)
            year = int(year_month[:4])
            if list_name not in lists:
                lists[list_name] = EmailList.objects.filter(name=list_name).first()
            email_list = lists[list_name]
            if email_list is None:
                continue
            if (list_name, year) not in small_years:
                small_years[(list_name, year)] = (
                    year < this_year and is_small_year(email_list, year))
            date = str(year) if small_years[(list_name, year)] else year_month
            for view in ('archive_browse_static_date', 'archive_browse_static_thread'):
                path = reverse(view, kwargs={'list_name': list_name, 'date': date})
                urls.add(settings.ARCHIVE_HOST_URL + path)
    return sorted(tags), sorted(urls)


def legacy_purge(refs):
    """Purge the cached pages built from refs from Cloudflare.

    Tags and urls go in separate requests: the API does not allow combining
    them in one call, and keeping them apart means a failure of one does not
    skip the other.
    """
    if not (settings.SERVER_MODE == 'production' and settings.USING_CDN):
        return
    tags, urls = legacy_purge_targets(refs)
    with Cloudflare(api_token=settings.CLOUDFLARE_AUTH_KEY) as cf:
        for field, values in (('tags', tags), ('files', urls)):
            for i in range(0, len(values), PURGE_CHUNK_SIZE):
                chunk = values[i:i + PURGE_CHUNK_SIZE]
                try:
                    cf.cache.purge(zone_id=settings.CLOUDFLARE_ZONE_ID, **{field: chunk})
                    logger.info(f'purging cached {field}: {chunk}')
                except APIError as e:
                    traceback.print_exc(file=sys.stdout)
                    logger.error(e)
                except requests.exceptions.HTTPError as e:
                    logger.error(e)
