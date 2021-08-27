# encoding: utf-8
from __future__ import absolute_import, division, print_function, unicode_literals

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Completely rebuilds the search index by removing the old data and then updating."

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput', action='store_false', dest='interactive', default=True,
            help='If provided, no prompts will be issued to the user and the data will be wiped out.'
        )
        parser.add_argument(
            '--nocommit', action='store_false', dest='commit',
            default=True, help='Will pass commit=False to the backend.'
        )
        parser.add_argument(
            '-b', '--batch-size', dest='batchsize', type=int, default=1000,
            help='Number of items to index at once.'
        )

    def handle(self, **options):
        clear_options = options.copy()
        update_options = options.copy()
        for key in ('batchsize', ):
            del clear_options[key]
        for key in ('interactive', ):
            del update_options[key]
        call_command('clear_index_new', **clear_options)
        call_command('update_index_new', **update_options)
