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
    'This just wraps the archive_message function so it can be queued in Celery'
    return archive_message(*args,**kwargs)

@app.task
def save_message(processor, sender, instance):
    'Save a message to the index.  Called from QueuedSignalProcessor'
    using_backends = processor.connection_router.for_write(instance=instance)

    for using in using_backends:
        try:
            index = processor.connections[using].get_unified_index().get_index(sender)
            index.update_object(instance, using=using)
        except NotHandled:
            # TODO: Maybe log it or let the exception bubble?
            pass

