# Copyright The IETF Trust 2026, All Rights Reserved
# -*- coding: utf-8 -*-


from django.core.management.base import BaseCommand, CommandError
from mlarchive.archive.utils import create_cf_worker_templates

import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create templates for Cloudflare workers"

    def handle(self, *args, **options):
        try:
            create_cf_worker_templates()
        except Exception as e:
            logger.error(f'create cloudflare worker templates failed: {e}')
            raise CommandError(f'Command failed. {e}')
