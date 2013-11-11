from celery import Celery

celery = Celery('tasks', backend='amqp', broker='amqp://guest@localhost//')
#celery.conf.CELERYD_CONCURRENCY=1
celery.config_from_object('celeryconfig')

import os

os.environ[ 'DJANGO_SETTINGS_MODULE' ] = "mlarchive.settings"

@celery.task
def add(x,y):
    return x + y

@celery.task
def add_mark(msg,bits):
    msg.mark(bits)
    print '%s:%s:%s' % (msg.msgid,msg.spam_score,bits)
    return None

