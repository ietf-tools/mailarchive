# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('error', models.CharField(max_length=255, blank=True)),
                ('description', models.CharField(max_length=255)),
                ('filename', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EmailList',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('active', models.BooleanField(default=True, db_index=True)),
                ('alias', models.CharField(max_length=255, blank=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('description', models.CharField(max_length=255, blank=True)),
                ('members_digest', models.CharField(max_length=28, blank=True)),
                ('name', models.CharField(unique=True, max_length=255, db_index=True)),
                ('private', models.BooleanField(default=False, db_index=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('members', models.ManyToManyField(to=settings.AUTH_USER_MODEL)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Legacy',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('email_list_id', models.CharField(max_length=40)),
                ('msgid', models.CharField(max_length=255, db_index=True)),
                ('number', models.IntegerField()),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('base_subject', models.CharField(max_length=512, blank=True)),
                ('cc', models.TextField(default=b'', blank=True)),
                ('date', models.DateTimeField(db_index=True)),
                ('frm', models.CharField(max_length=255, blank=True)),
                ('from_line', models.CharField(max_length=255, blank=True)),
                ('hashcode', models.CharField(max_length=28, db_index=True)),
                ('in_reply_to', models.TextField(default=b'', blank=True)),
                ('legacy_number', models.IntegerField(db_index=True, null=True, blank=True)),
                ('msgid', models.CharField(max_length=255, db_index=True)),
                ('references', models.TextField(default=b'', blank=True)),
                ('spam_score', models.IntegerField(default=0)),
                ('subject', models.CharField(max_length=512, blank=True)),
                ('to', models.TextField(default=b'', blank=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('email_list', models.ForeignKey(to='archive.EmailList')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Thread',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateTimeField(db_index=True)),
                ('first', models.ForeignKey(related_name='thread_key', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='archive.Message', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='message',
            name='thread',
            field=models.ForeignKey(to='archive.Thread'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='attachment',
            name='message',
            field=models.ForeignKey(to='archive.Message'),
            preserve_default=True,
        ),
    ]
