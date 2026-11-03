# Copyright The IETF Trust 2026, All Rights Reserved

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0007_storedobject_name_collation'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskLock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
