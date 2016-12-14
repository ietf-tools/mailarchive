# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime

from django.db import models, migrations

from mlarchive.archive.thread import get_references, get_in_reply_to

def get_references_or_reply_to_thread(message):
    Message = apps.get_model("archive", "Message")
    if message.references:
        msgids = get_references(message)
        for msgid in msgids:
            try:
                msg = Message.objects.get(email_list=message.email_list,msgid=msgid)
                return msg.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                pass
    if message.in_reply_to:
        msgid = get_in_reply_to(message)
        if msgid:
            try:
                msg = Message.objects.get(email_list=message.email_list,msgid=msgid)
                return msg.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                pass

def fix_threads(apps, schema_editor):
    '''Check each message since latest release.  If we find
    references or in-reply-to message in the same list get
    thread.  If that thread doesn't match message.thread,
    change it.
    '''
    Message = apps.get_model("archive", "Message")
    Thread = apps.get_model('archive', 'Thread')
    # earlier migration took place 12-04, start just before that
    abandoned_threads = set()
    start = datetime.datetime(2016,12,3)
    messages = Message.objects.filter(date__gte=start)
    for message in messages:
        thread = get_references_or_reply_to_thread(message)
        if thread and message.thread != thread:
            print "ID: {}-{}. {} => {}".format(message.id,message.email_list.name,message.thread,thread)
            abandoned_threads.add(message.thread)
            message.thread = thread
            message.save()

    # remove empty threads
    for thread in abandoned_threads:
        if thread.message_set.count() == 0:
            print "Removing empty thread: {}".format(thread)
            thread.delete()

def reverse_fix_threads(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0003_auto_20161026_1151'),
    ]

    operations = [
        migrations.RunPython(fix_threads, reverse_fix_threads),
    ]
