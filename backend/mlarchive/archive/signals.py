import logging
import os
import shutil

from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.dispatch import receiver
from django.db.models.signals import pre_delete, post_delete, post_save
from django.db import models, connection, transaction

from mlarchive.archive.models import Message, EmailList
from mlarchive.archive.backends.elasticsearch import ESBackend, get_identifier
from mlarchive.archive import derived
from mlarchive.archive.storage_utils import move_object, exists_in_storage
from mlarchive.archive.utils import _export_lists
from mlarchive.celeryapp import app

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Signal Handlers
# --------------------------------------------------

@receiver([post_save, post_delete], sender=EmailList)
def _clear_lists_cache(sender, instance, **kwargs):
    """If EmailList object is saved or deleted remove the list cache entries
    """
    cache.delete('lists')
    cache.delete('lists_public')


@receiver(pre_delete, sender=Message)
def _message_remove(sender, instance, **kwargs):
    """Move a removed message to the removed bucket and emit MessageRemoved.

    The message blob is moved to the "ml-messages-removed" bucket. A copy of
    the message on the filesystem, if there is one, is moved to the list's
    "_removed" directory.
    """
    # before set_first() below, so the refs include the month the thread is
    # listed under now, as well as the one it moves to
    derived.emit(derived.MessageRemoved(instance.pk))

    # move file on filesystem, if this message still has one
    path = instance.get_file_path()
    if os.path.exists(path):
        target_dir = instance.get_removed_dir()
        if not os.path.exists(target_dir):
            os.mkdir(target_dir)
            os.chmod(target_dir, 0o2777)
        target_path = os.path.join(target_dir, os.path.basename(path))
        if os.path.exists(target_path):
            os.remove(path)
        else:
            shutil.move(path, target_dir)
        logger.info('message file moved: {} => {}'.format(path, target_dir))

    # move blob
    blob_name = instance.get_blob_name()
    source_bucket = instance.get_blob_bucket()
    if exists_in_storage(source_bucket, blob_name):
        move_object(blob_name, source_bucket, 'ml-messages-removed')
        logger.info('message file moved: {} => {}'.format(blob_name, 'ml-messages-removed'))
    else:
        logger.warning('no blob to move for removed message [bucket={},name={}]'.format(
            source_bucket, blob_name))

    # if message is first of many in thread, should reset thread.first before
    # deleting
    if (instance.thread.first == instance and
            instance.thread.message_set.count() > 1):
        next_in_thread = instance.thread.message_set.order_by('date')[1]
        instance.thread.set_first(next_in_thread)


@receiver(post_save, sender=Message)
def _update_thread(sender, instance, **kwargs):
    """When messages are saved, udpate thread info
    """
    if not instance.thread.first or instance.date < instance.thread.date:
        instance.thread.set_first(instance)


@receiver(post_save, sender=EmailList)
def _list_save_handler(sender, instance, created, **kwargs):
    if created:
        _export_lists()

# --------------------------------------------------
# Helpers
# --------------------------------------------------


def _flush_noauth_cache(email_list):
    keys = ['{:04d}-noauth'.format(user.id) for user in email_list.members.all()]
    cache.delete_many(keys)


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
