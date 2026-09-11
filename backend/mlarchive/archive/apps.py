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
        self.check_artifact_storages()

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

    def check_artifact_storages(self):
        """Ensure every artifact storage alias equals its bucket_name.

        StoredObject.store and Blob.bucket hold the storage's bucket_name, while the
        rest of the code passes the STORAGES alias around as the kind, the bucket and
        the list's blob_bucket, and queries the index with it. That only works while
        the two names are the same, so fail at startup if a configuration ever makes
        them differ, instead of letting listings quietly come back empty.
        """
        from django.core.files.storage import storages, InvalidStorageError

        mismatched = []
        for name in settings.ARTIFACT_STORAGE_NAMES:
            try:
                bucket_name = getattr(storages[name], 'bucket_name', None)
            except InvalidStorageError:
                bucket_name = None
            if bucket_name != name:
                mismatched.append(f'{name} (bucket_name={bucket_name!r})')
        if mismatched:
            raise ImproperlyConfigured(
                'Every entry in settings.ARTIFACT_STORAGE_NAMES must name a STORAGES '
                'alias whose bucket_name equals the alias: {}'.format(', '.join(mismatched)))

    def import_class(self, path):
        path_bits = path.split('.')
        # Cut off the class name at the end.
        class_name = path_bits.pop()
        module_path = '.'.join(path_bits)
        module_itself = importlib.import_module(module_path)

        if not hasattr(module_itself, class_name):
            raise ImportError("The Python module '%s' has no '%s' class." % (module_path, class_name))

        return getattr(module_itself, class_name)
