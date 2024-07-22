import os
from celery import Celery
from celery.signals import setup_logging

from django.conf import settings


# Disable celery's internal logging configuration, we set it up via Django
@setup_logging.connect
def on_setup_logging(**kwargs):
    pass


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlarchive.settings.settings')

app = Celery('mlarchive')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
