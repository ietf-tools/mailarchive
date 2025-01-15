# Copyright The IETF Trust 2025, All Rights Reserved
# -*- coding: utf-8 -*-


from django.core.management.base import BaseCommand, CommandError
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import move_list

import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Move messages from source list to target list"

    def add_arguments(self, parser):
        parser.add_argument('source', help='Source list name')
        parser.add_argument('target', help='Target list name')

    def handle(self, *args, **options):
        source_name = options['source']
        # confirm source list exists
        try:
            _ = EmailList.objects.get(name=source_name)
        except EmailList.DoesNotExist:
            raise CommandError(f'Source list does not exist: {source_name}')
        try:
            move_list(options['source'], options['target'])
        except Exception as e:
            logger.error(f'move list failed: {e}')
            raise CommandError(f'Command failed. {e}')
