import importlib

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ArchiveConfig(AppConfig):
    name = 'mlarchive.archive'
    verbose_name = "Archive"
    signal_processor = None

    def ready(self):
        import mlarchive.archive.signals    # noqa

        self.check_inspectors()

        # Setup the signal processor.
        if not self.signal_processor:
            signal_processor_path = getattr(settings, 'ELASTICSEARCH_SIGNAL_PROCESSOR', 'mlarchive.archive.signals.BaseSignalProcessor')
            signal_processor_class = self.import_class(signal_processor_path)
            self.signal_processor = signal_processor_class(connections=None)

    def check_inspectors(self):
        """Ensure every name in settings.INSPECTORS resolves to an inspector class.
        Inspectors run on every incoming message, so an unknown name here would send
        all mail to the failed bucket.  Fail at startup instead.
        """
        from mlarchive.archive.inspectors import Inspector

        unknown = [name for name in getattr(settings, 'INSPECTORS', {})
                   if name.lower() not in Inspector.registry]
        if unknown:
            raise ImproperlyConfigured(
                'settings.INSPECTORS contains unknown inspectors: {}'.format(
                    ', '.join(unknown)))

    def import_class(self, path):
        path_bits = path.split('.')
        # Cut off the class name at the end.
        class_name = path_bits.pop()
        module_path = '.'.join(path_bits)
        module_itself = importlib.import_module(module_path)

        if not hasattr(module_itself, class_name):
            raise ImportError("The Python module '%s' has no '%s' class." % (module_path, class_name))

        return getattr(module_itself, class_name)
