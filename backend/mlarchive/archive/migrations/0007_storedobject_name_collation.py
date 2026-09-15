# Copyright The IETF Trust 2026, All Rights Reserved

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0006_storedobject'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storedobject',
            name='name',
            field=models.CharField(db_collation='C', max_length=1024),
        ),
    ]
