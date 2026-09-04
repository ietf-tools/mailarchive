import gzip
import logging
import tempfile
import os

import requests
from celery import Task, shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from mlarchive.archive.backends.elasticsearch import ESBackend
from mlarchive.celeryapp import app
from mlarchive.archive.utils import create_mbox_file
from mlarchive.archive.utils import get_membership
from mlarchive.archive.utils import get_subscriber_counts
from mlarchive.archive.utils import purge_incoming
from mlarchive.archive.utils import reconcile_stored_objects
from mlarchive.archive.utils import update_mbox_files
from mlarchive.archive.utils import init_private_list_members
from mlarchive.archive.utils import remove_selected
from mlarchive.archive.utils import mark_not_spam
from mlarchive.archive.utils import purge_confirmed_dupes
from mlarchive.archive.utils import import_message_blob
from mlarchive.archive.utils import load_hidden_messages
from mlarchive.archive.models import EmailList, Message, User
from mlarchive.archive.mail import Loader
from mlarchive.archive.message_json import store_message_json
from mlarchive.archive.storage import reconcile_bucket
from mlarchive.archive.utils import fetch_nav_for_batch

logger = logging.getLogger(__name__)

REBUILD_JSON_STOP_KEY = 'rebuild_messages_json_stop'
BLOBDB_QUEUE = 'blobdb'

# Registers the one-time backfill task; autodiscovery only scans <app>.tasks.
from mlarchive.archive.stored_object_backfill import backfill_stored_objects_task  # noqa: F401


class CelerySignalHandler(Task):
    using = settings.CELERY_HAYSTACK_DEFAULT_ALIAS
    max_retries = settings.CELERY_HAYSTACK_MAX_RETRIES
    default_retry_delay = settings.CELERY_HAYSTACK_RETRY_DELAY

    def split_identifier(self, identifier, **kwargs):
        """
        Break down the identifier representing the instance.

        Converts 'notes.note.23' into ('notes.note', 23).
        """
        bits = identifier.split('.')

        if len(bits) < 2:
            logger.error("Unable to parse object "
                         "identifer '%s'. Moving on..." % identifier)
            return (None, None)

        pk = bits[-1]
        # In case Django ever handles full paths...
        object_path = '.'.join(bits[:-1])
        return (object_path, pk)

    def get_model_class(self, object_path, **kwargs):
        """
        Fetch the model's class in a standarized way.
        """
        bits = object_path.split('.')
        app_name = '.'.join(bits[:-1])
        classname = bits[-1]
        model_class = apps.get_model(app_name, classname)

        if model_class is None:
            raise ImproperlyConfigured("Could not load model '%s'." %
                                       object_path)
        return model_class

    def get_instance(self, model_class, pk, **kwargs):
        """
        Fetch the instance in a standarized way.
        """
        instance = None
        try:
            instance = model_class._default_manager.get(pk=int(pk))
        except model_class.DoesNotExist:
            logger.error("Couldn't load %s.%s.%s. Somehow it went missing?" %
                         (model_class._meta.app_label.lower(),
                          model_class._meta.object_name.lower(), pk))
        except model_class.MultipleObjectsReturned:
            logger.error("More than one object with pk %s. Oops?" % pk)
        return instance

    def run(self, action, identifier, **kwargs):
        """
        Trigger the actual index handler depending on the
        given action ('update' or 'delete').
        """
        
        # First get the object path and pk (e.g. ('notes.note', 23))
        object_path, pk = self.split_identifier(identifier, **kwargs)
        if object_path is None or pk is None:
            msg = "Couldn't handle object with identifier %s" % identifier
            logger.error(msg)
            raise ValueError(msg)

        # Then get the model class for the object path
        model_class = self.get_model_class(object_path, **kwargs)
        backend = ESBackend()

        if action == 'delete':
            # If the object is gone, we'll use just the identifier
            # against the index.
            try:
                backend.remove(identifier)
            except Exception as exc:
                logger.exception(exc)
                self.retry(exc=exc)
            else:
                msg = ("Deleted '%s' (with %s)" %
                       (identifier, backend.index_name))
                logger.debug(msg)
                return msg
        elif action == 'update':
            # and the instance of the model class with the pk
            instance = self.get_instance(model_class, pk, **kwargs)
            if instance is None:
                logger.debug("Failed updating '%s' (with %s)" %
                             (identifier, backend.index_name))
                raise ValueError("Couldn't load object '%s'" % identifier)

            # Call the appropriate handler of the current index and
            # handle exception if neccessary
            try:
                backend.update([instance])
            except Exception as exc:
                logger.exception(exc)
                self.retry(exc=exc)
            else:
                msg = ("Updated '%s' (with %s)" %
                       (identifier, backend.index_name))
                logger.debug(msg)
                return msg
        else:
            logger.error("Unrecognized action '%s'. Moving on..." % action)
            raise ValueError("Unrecognized action %s" % action)


app.register_task(CelerySignalHandler())


@app.task
def remove_selected_task(user_id):
    remove_selected(user_id)


@app.task
def mark_not_spam_task(message_ids):
    mark_not_spam(message_ids)


# --------------------------------------------------
# Regular Shared Tasks
# --------------------------------------------------

@shared_task
def import_message_blob_task(bucket, name):
    import_message_blob(bucket, name)


@shared_task
def import_mbox_url_task(list_name, list_visibility, url):
    """Download an mbox file from url and import all messages into the archive."""
    response = None
    try:
        response = requests.get(url, timeout=(10, 60), stream=True)
        response.raise_for_status()
    except requests.RequestException as err:
        logger.error(f'import_mbox_url_task: failed to fetch {url}: {err}')
        if response is not None:
            response.close()
        return

    content_length = response.headers.get('Content-Length')
    if content_length is not None:
        try:
            if int(content_length) > settings.IMPORT_MBOX_MAX_SIZE:
                logger.error(
                    f'import_mbox_url_task: {url} Content-Length {content_length} '
                    f'exceeds limit {settings.IMPORT_MBOX_MAX_SIZE}'
                )
                response.close()
                return
        except ValueError:
            pass

    content_type = response.headers.get('Content-Type', '')
    is_gzip = content_type in ('application/x-gzip', 'application/gzip')

    temp_files = []
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as raw_f:
            raw_path = raw_f.name
            temp_files.append(raw_path)
            for chunk in response.iter_content(chunk_size=65536):
                raw_f.write(chunk)

        if is_gzip:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mbox') as mbox_f:
                mbox_path = mbox_f.name
                temp_files.append(mbox_path)
                with gzip.open(raw_path, 'rb') as gz_in:
                    for chunk in iter(lambda: gz_in.read(65536), b''):
                        mbox_f.write(chunk)
            import_path = mbox_path
        else:
            import_path = raw_path

        private = list_visibility == 'private'
        loader = Loader(import_path, listname=list_name, private=private)
        loader.process()
        logger.info(f'import_mbox_url_task: imported {url} into {list_name}, stats={loader.stats}')
    except Exception as err:
        logger.exception(f'import_mbox_url_task: failed for {url}: {err}')
    finally:
        response.close()
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass


# --------------------------------------------------
# Celery Beat Tasks
# --------------------------------------------------


@shared_task
def get_membership_task():
    '''Get list membership from mailman'''
    try:
        get_membership(quiet=True)
    except Exception as err:
        logger.error(f"Error in get_membership_task: {err}")


@shared_task
def get_subscriber_counts_task():
    '''Get subscriber counts for each list from mailman'''
    try:
        get_subscriber_counts()
    except Exception as err:
        logger.error(f"Error in get_subscriber_counts_task: {err}")


@shared_task
def purge_incoming_task():
    '''Purge messages older than 90 days from incoming dir'''
    try:
        purge_incoming()
    except Exception as err:
        logger.error(f"Error in purge_incoming_task: {err}")


@shared_task
def reconcile_stored_objects_task(bucket=None, repair=False):
    """Check the StoredObject index against storage, repairing drift if repair is set.

    The scheduled entry in periodic_tasks passes repair=True: the index is only
    trustworthy because this task keeps it so, and every repair moves a row towards
    the bytes, never the other way. Run by hand with the default for a report only.
    """
    try:
        reconcile_stored_objects(bucket=bucket, repair=repair)
    except Exception as err:
        logger.error(f"Error in reconcile_stored_objects_task: {err}")


@shared_task
def update_mbox_files_task():
    '''Update archive mbox files'''
    try:
        update_mbox_files()
    except Exception as err:
        logger.error(f"Error in update_mbox_files_task: {err}")


@shared_task
def init_private_list_members_task():
    '''Initialize the private list membership'''
    try:
        init_private_list_members()
    except Exception as err:
        logger.error(f"Error in init_private_list_members_task: {err}")


@shared_task
def purge_confirmed_dupes_task():
    '''Crawl [listname]/_dupes directories in archive and delete confirmed
    duplicate messages'''
    try:
        purge_confirmed_dupes()
    except Exception as err:
        logger.error(f"Error in purge_confirmed_dupes_task: {err}")


@shared_task
def load_hidden_messages_task(directory, listname=None):
    '''Crawl [listname]/_[directory] directories in archive and load message files
    into the ml-messages-[directory] blob storage bucket'''
    try:
        load_hidden_messages(directory, listname=listname)
    except Exception as err:
        logger.error(f"Error in load_hidden_messages_task: {err}")


def queue_depth(queue_name=BLOBDB_QUEUE):
    """Return the number of messages waiting on the broker in queue_name."""
    with app.connection_or_acquire() as connection:
        declared = connection.default_channel.queue_declare(queue=queue_name, passive=True)
    return declared.message_count


@shared_task
def rebuild_messages_json(
    start_after_pk=0,
    batch_size=1000,
    start_date=None,
    end_date=None,
    email_lists=None,
    countdown=30,
    max_queue_depth=100,
):
    """Rewrite the ml-messages-json object for one batch of messages, then self-chain.

    Each object is written through store_message_json, the same path a newly archived
    message takes, so the bytes, the StoredObject row and the replication event for R2
    all follow from one call. The replicator carries the batch to R2 one object at a
    time. Because this task runs on the same single-consumer queue as those events,
    its next invocation sits behind the batch's events in FIFO order and cannot start
    until they are consumed, so the rebuild cannot outrun the replicator and a normal
    message's replication waits behind at most one batch. Batch size sets that ceiling.
    As a guard for the cases ordering does not cover, chiefly a burst of normal
    traffic, an invocation first checks the depth of the blobdb queue and, if more than
    max_queue_depth messages are waiting, re-schedules itself unchanged after countdown
    seconds. A failing depth check is left to propagate, ending the chain; resume by
    hand once the broker answers.

    A message that fails to write is logged and counted, and the batch continues.
    When the batch is empty the rebuild is complete, and ml-messages-json is
    reconciled without repair as a check that every rewritten object is indexed.

    Dispatched by hand, on the blobdb queue. Filters narrow the run: start_date and
    end_date bound Message.date (ISO 8601, end exclusive), email_lists is a list of
    list names.

    To kick off:   rebuild_messages_json.apply_async(queue='blobdb')
                   rebuild_messages_json.apply_async(
                       queue='blobdb', kwargs={'email_lists': ['ietf'], 'batch_size': 500})
    To stop:       cache.set('rebuild_messages_json_stop', True, timeout=None)
    To resume:     cache.delete('rebuild_messages_json_stop')
                   rebuild_messages_json.apply_async(
                       queue='blobdb', kwargs={'start_after_pk': <last logged pk>})
    """
    if cache.get(REBUILD_JSON_STOP_KEY):
        logger.info(
            'rebuild_messages_json: halted by stop flag, resume with start_after_pk=%d',
            start_after_pk)
        return

    kwargs = dict(
        start_after_pk=start_after_pk,
        batch_size=batch_size,
        start_date=start_date,
        end_date=end_date,
        email_lists=email_lists,
        countdown=countdown,
        max_queue_depth=max_queue_depth,
    )

    depth = queue_depth()
    if depth > max_queue_depth:
        logger.info(
            'rebuild_messages_json: %d messages queued on %s, waiting %ds before the batch '
            'after pk=%d', depth, BLOBDB_QUEUE, countdown, start_after_pk)
        rebuild_messages_json.apply_async(kwargs=kwargs, countdown=countdown, queue=BLOBDB_QUEUE)
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
        stats = reconcile_bucket('ml-messages-json')
        logger.info('rebuild_messages_json: reconcile ml-messages-json: %s', stats)
        return

    public = [message for message in batch if not message.email_list.private]
    nav_map = fetch_nav_for_batch(public)
    written = failures = 0
    for message in public:
        try:
            store_message_json(message, nav=nav_map.get(message.pk))
            written += 1
        except Exception as err:
            failures += 1
            logger.error(
                'rebuild_messages_json: failed to write %s: %r', message.get_blob_name(), err)

    last_pk = batch[-1].pk
    logger.info(
        'rebuild_messages_json: batch done, last_pk=%d, written=%d, private=%d, failures=%d',
        last_pk, written, len(batch) - len(public), failures)

    kwargs['start_after_pk'] = last_pk
    rebuild_messages_json.apply_async(kwargs=kwargs, countdown=countdown, queue=BLOBDB_QUEUE)
