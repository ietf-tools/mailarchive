from django.apps import AppConfig


class ArchiveConfig(AppConfig):
    name = 'mlarchive.archive'
    verbose_name = "Archive"

    def ready(self):
        import mlarchive.archive.signals    # noqa
