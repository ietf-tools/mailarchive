#!../../../env/bin/python
'''
Related to Ticket #2197
https://trac.tools.ietf.org/tools/ietfdb/ticket/2197

Locate threads that don't have a "first" value and fix

'''
# Standalone broilerplate -------------------------------------------------------------
from .django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import re
import datetime

from mlarchive.archive.models import Thread

def get_first(thread):
    '''Get first message in thread by date.  Display warning if it doesn't match
    thread_order
    '''
    oldest = thread.message_set.order_by('date').first()
    first = thread.message_set.order_by('thread_order').first()
    if first != oldest:
        print("Warning: first != oldest ({})".format(thread))
    return oldest

deleted = 0
threads = Thread.objects.filter(first__isnull=True)

for thread in threads:
    first = get_first(thread)
    if first is None:
        thread.delete()
        deleted = deleted + 1
    else:
        thread.first = first
        thread.save()

print('Threads processed: {}'.format(threads.count()))
print('Empty Threads deleted: {}'.format(deleted))