import os
import celery

from django.conf import settings


# Disable celery's internal logging configuration, we set it up via Django
@celery.signals.setup_logging.connect
def on_setup_logging(**kwargs):
    pass


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlarchive.settings.settings')

app = celery.Celery('mlarchive')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
