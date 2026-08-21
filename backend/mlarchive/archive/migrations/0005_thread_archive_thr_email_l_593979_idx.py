# Copyright The IETF Trust 2026, All Rights Reserved

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0004_mailmanmember_useremail_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='thread',
            index=models.Index(fields=['email_list', 'date'], name='archive_thr_email_l_593979_idx'),
        ),
    ]
