# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='thread_depth',
            field=models.IntegerField(default=0),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='message',
            name='thread_order',
            field=models.IntegerField(default=0),
            preserve_default=True,
        ),
    ]
