from haystack.signals import BaseSignalProcessor
from django.db import models
from mlarchive.archive.tasks import save_message

class QueuedSignalProcessor(BaseSignalProcessor):
    # Override the built-in.
    def setup(self):
        models.signals.post_save.connect(self.enqueue_save)
        models.signals.post_delete.connect(self.enqueue_delete)

    # Override the built-in.
    def teardown(self):
        models.signals.post_save.disconnect(self.enqueue_save)
        models.signals.post_delete.disconnect(self.enqueue_delete)

    # Add on a queuing method.
    def enqueue_save(self, sender, instance, **kwargs):
        # Push the save & information onto queue du jour here...
        result = save_message.delay(self, sender, instance)

    # Add on a queuing method.
    def enqueue_delete(self, sender, instance, **kwargs):
        # Push the delete & information onto queue du jour here...
        using_backends = self.connection_router.for_write(instance=instance)

        for using in using_backends:
            try:
                index = self.connections[using].get_unified_index().get_index(sender)
                index.remove_object(instance, using=using)
            except NotHandled:
                # TODO: Maybe log it or let the exception bubble?
                pass
