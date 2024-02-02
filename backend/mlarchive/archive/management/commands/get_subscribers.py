# encoding: utf-8

from django.core.management import call_command
from django.core.management.base import BaseCommand
from mlarchive.archive.utils import get_subscriber_count

class Command(BaseCommand):
    help = "Get subscriber counts from mailman."

    def handle(self, **options):
        get_subscriber_count()
