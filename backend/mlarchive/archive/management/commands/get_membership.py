# encoding: utf-8

from django.core.management.base import BaseCommand
from mlarchive.archive.utils import get_membership_3


class Command(BaseCommand):
    help = "Get private list membership from mailman 3 API."

    def add_arguments(self, parser):
        parser.add_argument('-q', '--quiet', action='store_true', dest='quiet', default=False,
            help="Don't print lists as they are processed")

    def handle(self, *args, **options):
        get_membership_3(quiet=options['quiet'])
