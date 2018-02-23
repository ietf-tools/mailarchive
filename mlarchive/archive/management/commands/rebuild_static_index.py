
import os


from django.core.management.base import BaseCommand, CommandError

from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import rebuild_static_index

import logging
logger = logging.getLogger('mlarchive.custom')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


# --------------------------------------------------
# Classes
# --------------------------------------------------


class Command(BaseCommand):
    help = 'Imports message(s) into the archive'

    def add_arguments(self, parser):
        parser.add_argument('-l', '--listname', dest='listname',
            help='specify the name of the email list'),


    def handle(self, *args, **options):
        stats = {}
        print options
        if options['listname']:
            try:
                elist = EmailList.objects.get(name=options['listname'])
            except EmailList.DoesNotExist:
                raise CommandError('{} not a valid list'.format(options['listname']))
            rebuild_static_index(elist)
        else:
            rebuild_static_index()
