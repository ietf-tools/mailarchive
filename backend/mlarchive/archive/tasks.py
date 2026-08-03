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
from mlarchive.archive.utils import update_mbox_files
from mlarchive.archive.utils import init_private_list_members
from mlarchive.archive.utils import remove_selected
from mlarchive.archive.utils import mark_not_spam
from mlarchive.archive.utils import purge_confirmed_dupes
from mlarchive.archive.utils import import_message_blob
from mlarchive.archive.utils import load_hidden_messages
from mlarchive.archive.models import EmailList, Message, User
from mlarchive.archive.mail import Loader

logger = logging.getLogger(__name__)


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
        logger.error(f'import_mbox_url_task: failed for {url}: {err}')
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
