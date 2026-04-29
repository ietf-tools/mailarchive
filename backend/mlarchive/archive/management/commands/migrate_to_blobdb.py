# Copyright The IETF Trust 2025, All Rights Reserved

from django.core.management.base import BaseCommand

import logging
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Enqueue migration of message archive files to blobdb and R2.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-after-pk',
            type=int,
            default=0,
            help='Skip messages with pk <= this value (default: 0)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Messages per batch (default: 1000)',
        )
        parser.add_argument(
            '--start-date',
            default=None,
            help='Only include messages with date >= this value (ISO 8601, e.g. 2024-01-01)',
        )
        parser.add_argument(
            '--end-date',
            default=None,
            help='Only include messages with date < this value (ISO 8601, e.g. 2025-01-01)',
        )
        parser.add_argument(
            '--email-lists',
            nargs='+',
            default=None,
            metavar='LIST',
            help='Only include messages from these lists (space-separated)',
        )
        parser.add_argument(
            '--max-workers',
            type=int,
            default=50,
            help='Thread pool size for R2 replication (default: 50)',
        )
        parser.add_argument(
            '--countdown',
            type=int,
            default=30,
            help='Seconds to wait between batches (default: 30)',
        )

    def handle(self, *args, **options):
        from mlarchive.blobdb.tasks import migrate_messages_to_blobdb

        kwargs = dict(
            start_after_pk=options['start_after_pk'],
            batch_size=options['batch_size'],
            start_date=options['start_date'],
            end_date=options['end_date'],
            email_lists=options['email_lists'],
            max_workers=options['max_workers'],
            countdown=options['countdown'],
        )

        result = migrate_messages_to_blobdb.apply_async(queue='blobdb', kwargs=kwargs)

        self.stdout.write(self.style.SUCCESS(f'Migration enqueued. task_id={result.id}'))
        self.stdout.write('To stop:   python manage.py shell -c "from django.core.cache import cache; cache.set(\'migrate_messages_to_blobdb_stop\', True, timeout=None)"')
        self.stdout.write('To resume: python manage.py migrate_to_blobdb --start-after-pk=<last logged pk>')
