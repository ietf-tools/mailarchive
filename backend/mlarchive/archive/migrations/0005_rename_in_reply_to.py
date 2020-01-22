# -*- coding: utf-8 -*-


from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0004_fix_threads'),
    ]

    operations = [
        migrations.RenameField('Message', 'in_reply_to', 'in_reply_to_value'),
    ]
