# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

from mlarchive.archive.models import Message, get_in_reply_to_message


def get_replies(apps, schema_editor):
    '''Traverse all message records, read in_reply_to_value and 
    populate in_reply_to FK'''
    Message = apps.get_model("archive", "Message")

    for message in Message.objects.all():
        reply_message = get_in_reply_to_message(
            message.in_reply_to_value,
            message.email_list)
        if reply_message:        
            message.in_reply_to = reply_message
            message.save()


def reverse_get_replies(apps, schema_editor):
    Message.objects.all().update(in_reply_to=None)


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0006_message_in_reply_to'),
    ]

    operations = [
        migrations.RunPython(get_replies, reverse_get_replies),
    ]
