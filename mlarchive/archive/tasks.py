from __future__ import absolute_import

from mlarchive.celery import app

@app.task
def add(x, y):
    return x + y

@app.task
def add_mark(msg,bits):
    msg.mark(bits)
    print '%s:%s:%s' % (msg.msgid,msg.spam_score,bits)
    return None
