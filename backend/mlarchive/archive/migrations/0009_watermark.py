# Copyright The IETF Trust 2026, All Rights Reserved

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0008_tasklock'),
    ]

    operations = [
        migrations.CreateModel(
            name='Watermark',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('value', models.DateTimeField()),
            ],
        ),
    ]
