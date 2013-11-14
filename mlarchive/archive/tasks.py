from __future__ import absolute_import

from mlarchive.celeryapp import app

@app.task
def add(x, y):
    return x + y

@app.task
def add_mark(msg,bits):
    msg.mark(bits)
    print '%s:%s:%s' % (msg.msgid,msg.spam_score,bits)
    return None

@app.task
def call_archive_message(*args,**kwargs):
    '''
    This just wraps the archive_message function so it can be queued in Celery
    '''
    return archive_message(*args,**kwargs)
