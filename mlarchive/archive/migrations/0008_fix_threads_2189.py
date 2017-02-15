'''Locate messages that are the first in their thread, that have no References
or In-Reply-To headers, and should have been matched to an existing thread from the
subject line but weren't, and merge to that thread.

NOTE: run with --settings=noindex and update_index after completion
'''
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import datetime

from django.db import models, migrations
from mlarchive.archive.management.commands._classes import subject_is_reply
from mlarchive.archive.thread import compute_thread

START_DATE = datetime.datetime(2016,11,1)   # release 1.5.0

def fix_threads(apps, schema_editor):
    Thread = apps.get_model('archive', 'Thread')
    Message = apps.get_model('archive', 'Message')
    total = 0
    threads = Thread.objects.filter(date__gte=START_DATE).order_by('date')
    for thread in threads:
        msg = thread.first
        # check subject
        if subject_is_reply(msg.subject):
            messages = Message.objects.filter(email_list=msg.email_list,
                                              date__lt=msg.date,
                                              base_subject=msg.base_subject).order_by('-date')
            if messages:
                found_thread = messages[0].thread
            else:
                continue

            print "Moving message:{} from thread:{} to thread:{}".format(msg.pk,thread.pk,found_thread.pk)
            if thread == found_thread:
                print "WARNING: same thread"
                continue
            total = total + 1
            for message in thread.message_set.all():
                message.thread = found_thread
                message.save()
            compute_thread(found_thread)
            assert thread.message_set.count() == 0
            thread.delete()

    print "Total: {}".format(total)

def reverse_fix_threads(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0007_populate_in_reply_to'),
    ]

    operations = [
        migrations.RunPython(fix_threads, reverse_fix_threads),
    ]
