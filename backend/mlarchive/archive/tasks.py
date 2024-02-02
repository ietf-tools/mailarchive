import logging

from celery import Task, shared_task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from mlarchive.archive.backends.elasticsearch import ESBackend
from mlarchive.celeryapp import app
from mlarchive.archive.utils import create_mbox_file
from mlarchive.archive.models import EmailList

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


@app.task
def update_mbox(files):
    for file in files:
        elist = EmailList.objects.get(pk=file[2])
        create_mbox_file(file[0], file[1], elist)


CelerySignalHandler = app.register_task(CelerySignalHandler())
# CeleryHaystackUpdateIndex = app.register_task(CeleryHaystackUpdateIndex())


@shared_task
def get_subscribers():
    '''Get subscriber counts from mailman 2'''

    try:
        call_command('get_subscribers')
    except RuntimeError as err:
        logger.info(f"Error in get_subscribers: {err}")
