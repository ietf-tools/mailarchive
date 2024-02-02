# encoding: utf-8

import requests

from django.config import settings
from django.core.management.base import BaseCommand, CommandError
from mlarchive.archive.utils import get_subscriber_counts

import logging
logger = logging.getLogger(__name__)


def confirm_settings(names):
    for name in names:
        if not hasattr(settings, name):
            raise CommandError(f'{name} missing from settings')
        if not getattr(settings, name):
            raise CommandError(f'setting {name} empty')


class Command(BaseCommand):
    help = "Get list sunscriber counts from mailman 3 API."

    def handle(self, *args, **options):
        confirm_settings([
            'MAILMAN_API_USER',
            'MAILMAN_API_PASSWORD',
            'MAILMAN_API_ORIGIN',
            'MAILMAN_API_LISTS',
            'MAILMAN_API_MEMBER'])
        try:
            get_subscriber_counts()
        except requests.RequestException as e:
            logger.error(f'command get_subscriber_counts failed: {e}')
            raise CommandError(f'Command failed. {e}')
