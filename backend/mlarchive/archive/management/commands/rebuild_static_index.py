
import os

from django.core.management.base import BaseCommand, CommandError

from mlarchive.archive.models import EmailList
from mlarchive.archive.views_static import rebuild_static_index


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


# --------------------------------------------------
# Classes
# --------------------------------------------------


class Command(BaseCommand):
    help = 'Rebuild static index pages'

    def add_arguments(self, parser):
        parser.add_argument('-l', '--listname', dest='listname',
            help='specify the name of the email list')
        parser.add_argument('--resume', action='store_true', dest='resume', default=False,
            help='resume full rebuild from given list')

    def handle(self, *args, **options):
        stats = {}
        print(options)
        if options['resume'] and not options['listname']:
            raise CommandError('Must provide listname with --resume option')

        if options['listname']:
            try:
                elist = EmailList.objects.get(name=options['listname'])
            except EmailList.DoesNotExist:
                raise CommandError('{} not a valid list'.format(options['listname']))
            rebuild_static_index(elist, resume=options['resume'])
        else:
            rebuild_static_index()
