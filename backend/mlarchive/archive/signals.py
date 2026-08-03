import io
import logging
import os
import requests
import shutil
import sys
import traceback
from cloudflare import Cloudflare, APIError

from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.dispatch import receiver
from django.db.models.signals import pre_delete, post_delete, post_save
from django.db import models, connection, transaction

from mlarchive.archive.models import Message, EmailList
from mlarchive.archive.backends.elasticsearch import ESBackend, get_identifier
from mlarchive.archive.storage_utils import store_file, remove_from_storage, move_object
from mlarchive.archive.utils import _export_lists
from mlarchive.celeryapp import app

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Signal Handlers
# --------------------------------------------------

@receiver(post_save, sender=Message)
def _save_message_json(sender, instance, created, **kwargs):
    '''Save ml-messages-json blob for use in Cloudflare worker edge response'''
    if not instance.email_list.private and created:
        store_file(
            kind='ml-messages-json',
            name=instance.get_blob_name(),
            file=io.BytesIO(instance.as_json().encode('utf-8')),
            allow_overwrite=True,
            content_type='application/json'
        )
        if instance.thread_order > 0:
            update_message_json_thread(instance)
        update_message_json_list(instance)


@receiver([post_save, post_delete], sender=EmailList)
def _clear_lists_cache(sender, instance, **kwargs):
    """If EmailList object is saved or deleted remove the list cache entries
    """
    cache.delete('lists')
    cache.delete('lists_public')


@receiver(pre_delete, sender=Message)
def _message_remove(sender, instance, **kwargs):
    """When messages are removed, via the admin page, we need to move the message
    archive file to the "_removed" directory and purge the cache
    """
    # move file on filesystem
    path = instance.get_file_path()
    if not os.path.exists(path):
        return
    target_dir = instance.get_removed_dir()
    if not os.path.exists(target_dir):
        os.mkdir(target_dir)
        os.chmod(target_dir, 0o2777)
    target_path = os.path.join(target_dir, os.path.basename(path))
    if os.path.exists(target_path):
        os.remove(path)
    else:
        shutil.move(path, target_dir)

    # move blob
    if instance.email_list.private:
        source = 'ml-messages-private'
    else:
        source = 'ml-messages'
    move_object(instance.get_blob_name(), source, 'ml-messages-removed')

    # delete blob from ml-messages-json bucket
    # Ok if it's not there, a private message wouldn't be
    remove_from_storage(kind='ml-messages-json', name=instance.get_blob_name(), warn_if_missing=False)

    logger.info('message file moved: {} => {}'.format(path, target_dir))

    # if message is first of many in thread, should reset thread.first before
    # deleting
    if (instance.thread.first == instance and
            instance.thread.message_set.count() > 1):
        next_in_thread = instance.thread.message_set.order_by('date')[1]
        instance.thread.set_first(next_in_thread)

    # handle cache
    if settings.SERVER_MODE == 'production' and settings.USING_CDN:
        purge_files_from_cache(instance)


@receiver(post_save, sender=Message)
def _update_thread(sender, instance, **kwargs):
    """When messages are saved, udpate thread info
    """
    if not instance.thread.first or instance.date < instance.thread.date:
        instance.thread.set_first(instance)


@receiver(post_save, sender=Message)
def _purge_cache(sender, instance, created, **kwargs):
    if created and settings.SERVER_MODE == 'production' and settings.USING_CDN:
        purge_files_from_cache(instance)


@receiver(post_save, sender=EmailList)
def _list_save_handler(sender, instance, created, **kwargs):
    if created:
        _export_lists()

# --------------------------------------------------
# Helpers
# --------------------------------------------------


def get_purge_cache_tags(message):
    """Returns the list of Cloudflare Cache-Tags to purge when a message is
    created or deleted.

    Message pages (detail and ajax) are tagged by thread, so purging the
    message's thread tag invalidates every message in that thread at once.
    The next and previous messages by list order live in adjacent threads and
    have stale next/previous links, so their thread tags are purged too. This
    over-purges those two neighbor threads, which is bounded and correct.
    """
    tags = [message.get_cache_tag()]
    next_in_list = message.next_in_list()
    if next_in_list:
        tags.append(next_in_list.get_cache_tag())
    previous_in_list = message.previous_in_list()
    if previous_in_list:
        tags.append(previous_in_list.get_cache_tag())
    # dedupe
    return list(set(tags))


def get_purge_cache_urls(message, created=True):
    """Returns a list of absolute urls to purge from cache when a message is
    created or deleted.

    Only the static index pages are purged by url; the message pages
    themselves are purged by Cache-Tag (see get_purge_cache_tags).
    """
    return message.get_absolute_static_index_urls()


def purge_files_from_cache(message, created=True):
    """Purge a message's cached pages from Cloudflare.

    Message pages are purged by Cache-Tag (whole thread at a time) and the
    static index pages are purged by url. These are two independent Cloudflare
    requests - the API does not allow combining ``tags`` and ``files`` in a
    single call, and keeping them separate means a failure of one does not
    skip the other.

    2026-07-09 NOTE: if later expanding the set of tags or urls to purge, first
    consult the Cloudflare limits,
    https://developers.cloudflare.com/cache/how-to/purge-cache/#availability-and-limits
    """
    tags = get_purge_cache_tags(message)
    urls = get_purge_cache_urls(message, created)
    with Cloudflare(api_token=settings.CLOUDFLARE_AUTH_KEY) as cf:
        try:
            cf.cache.purge(zone_id=settings.CLOUDFLARE_ZONE_ID, tags=tags)
            logger.info(f'purging cached tags: {tags}')
        except APIError as e:
            traceback.print_exc(file=sys.stdout)
            logger.error(e)
        except requests.exceptions.HTTPError as e:
            logger.error(e)
        try:
            cf.cache.purge(zone_id=settings.CLOUDFLARE_ZONE_ID, files=urls)
            logger.info(f'purging cached urls: {urls}')
        except APIError as e:
            traceback.print_exc(file=sys.stdout)
            logger.error(e)
        except requests.exceptions.HTTPError as e:
            logger.error(e)


def _flush_noauth_cache(email_list):
    keys = ['{:04d}-noauth'.format(user.id) for user in email_list.members.all()]
    cache.delete_many(keys)


def update_message_json_thread(message):
    '''Write ml-messages-json for all other messages in thread
    TODO: consider alternatives like client retrieving thread instead of computing
    '''
    for msg in message.thread.message_set.exclude(pk=message.pk):
        store_file(
            kind='ml-messages-json',
            name=msg.get_blob_name(),
            file=io.BytesIO(msg.as_json().encode('utf-8')),
            allow_overwrite=True,
            content_type='application/json'
        )


def update_message_json_list(message):
    '''Write ml-messages-json for the previous message in list order.
    Its next_in_list link becomes stale when a new message is added after it.
    '''
    prev_msg = message.previous_in_list()
    if prev_msg:
        store_file(
            kind='ml-messages-json',
            name=prev_msg.get_blob_name(),
            file=io.BytesIO(prev_msg.as_json().encode('utf-8')),
            allow_overwrite=True,
            content_type='application/json'
        )

# --------------------------------------------------
# Classes
# --------------------------------------------------

class BaseSignalProcessor(object):
    """
    A convenient way to attach to Django's signals & cause things to
    index.

    By default, does nothing with signals but provides underlying functionality.
    """
    def __init__(self, connections):
        self.connections = connections
        self.backend = ESBackend()
        self.setup()

    def setup(self):
        """
        A hook for setting up anything necessary for
        ``handle_save/handle_delete`` to be executed.

        Default behavior is to do nothing (``pass``).
        """
        # Do nothing.
        pass

    def teardown(self):
        """
        A hook for tearing down anything necessary for
        ``handle_save/handle_delete`` to no longer be executed.

        Default behavior is to do nothing (``pass``).
        """
        # Do nothing.
        pass

    def handle_save(self, sender, instance, **kwargs):
        """
        Given an individual model instance, update the index
        """
        try:
            self.backend.update([instance])
        except Exception:
            # TODO: Maybe log it or let the exception bubble?
            pass

    def handle_delete(self, sender, instance, **kwargs):
        """
        Given an individual model instance, delete from index.
        """
        try:
            self.backend.remove(instance)
        except Exception:
            # TODO: Maybe log it or let the exception bubble?
            pass


class RealtimeSignalProcessor(BaseSignalProcessor):
    """
    Allows for observing when saves/deletes fire & automatically updates the
    search engine appropriately.
    """
    def setup(self):
        models.signals.post_save.connect(self.handle_save, sender=Message)
        models.signals.post_delete.connect(self.handle_delete, sender=Message)

    def teardown(self):
        models.signals.post_save.disconnect(self.handle_save, sender=Message)
        models.signals.post_delete.disconnect(self.handle_delete, sender=Message)


class CelerySignalProcessor(BaseSignalProcessor):

    def setup(self):
        models.signals.post_save.connect(self.enqueue_save, sender=Message)
        models.signals.post_delete.connect(self.enqueue_delete, sender=Message)

    def teardown(self):
        models.signals.post_save.disconnect(self.enqueue_save, sender=Message)
        models.signals.post_delete.disconnect(self.enqueue_delete, sender=Message)

    def enqueue_save(self, sender, instance, **kwargs):
        return self.enqueue('update', instance, sender, **kwargs)

    def enqueue_delete(self, sender, instance, **kwargs):
        return self.enqueue('delete', instance, sender, **kwargs)

    def enqueue(self, action, instance, sender, **kwargs):
        enqueue_task(action, instance)
        return


def enqueue_task(action, instance, **kwargs):
    """
    Common utility for enqueing a task for the given action and
    model instance.
    """
    identifier = get_identifier(instance)

    task = get_update_task()
    task_func = lambda: task.apply_async((action, identifier), kwargs) # noqa

    if hasattr(transaction, 'on_commit'):
        # Django 1.9 on_commit hook
        transaction.on_commit(
            task_func
        )
    elif hasattr(connection, 'on_commit'):
        # Django-transaction-hooks
        connection.on_commit(
            task_func
        )
    else:
        task_func()


def get_update_task(name=None):
    task_name = name or settings.CELERY_DEFAULT_TASK
    task = app.tasks.get(task_name)
    if task is None:
        import mlarchive.archive.tasks  # noqa: ensure tasks are registered
        task = app.tasks.get(task_name)
    if task:
        return task
    else:
        raise ImproperlyConfigured(f'Invalid task name {task_name}')
