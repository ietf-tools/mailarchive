from __future__ import absolute_import, division, print_function, unicode_literals

from django.apps import AppConfig


class ArchiveConfig(AppConfig):
    name = 'mlarchive.archive'
    verbose_name = "Archive"

    def ready(self):
        import mlarchive.archive.signals    # noqa
