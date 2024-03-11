# encoding: utf-8

from django.conf import settings
from django.core.management.base import BaseCommand

from mlarchive.archive.backends.elasticsearch import ESBackend


class Command(BaseCommand):
    help = "Initializes the search index if it doesn't exist"

    def handle(self, **options):        
        backend = ESBackend()
        backend.setup()     # no-op if already exists
