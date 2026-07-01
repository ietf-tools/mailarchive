# Copyright The IETF Trust 2025, All Rights Reserved
# -*- coding: utf-8 -*-


from django.core.management.base import BaseCommand
from mlarchive.archive.utils import purge_incoming_dir

import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ("Purge files from INCOMING_DIR on disk, removing only those confirmed as "
            "archived elsewhere or marked no-archive.")

    def handle(self, *args, **options):
        stats = purge_incoming_dir()
        self.stdout.write('purge_incoming_dir results:')
        self.stdout.write(f'  scanned:             {stats.get("scanned", 0)}')
        self.stdout.write(f'  purged (archived):   {stats.get("purged", 0)}')
        self.stdout.write(f'  purged (no-archive): {stats.get("purged_no_archive", 0)}')
        self.stdout.write(f'  kept (no match):     {stats.get("kept", 0)}')
        self.stdout.write(f'  errors:              {stats.get("errors", 0)}')
