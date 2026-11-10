# Copyright The IETF Trust 2026, All Rights Reserved

"""Point the scheduled "Update MBOX" task at rebuild_touched_months_task.

update_mbox_files_task is gone, so a beat entry still naming it would send a
task no worker knows. The entry keeps its enabled flag and moves from daily to
hourly. Nothing happens where the entry was never created.
"""

from django.db import migrations
from django.utils import timezone

OLD_TASK = 'mlarchive.archive.tasks.update_mbox_files_task'
OLD_NAME = 'Update MBOX'
OLD_DESCRIPTION = 'Update archive MBOX files'
OLD_CRONTAB = dict(minute='5', hour='0', day_of_month='*', month_of_year='*', day_of_week='*')

NEW_TASK = 'mlarchive.archive.tasks.rebuild_touched_months_task'
NEW_NAME = 'Rebuild touched month files'
NEW_DESCRIPTION = 'Rebuild the month files of messages changed since the last run'
NEW_CRONTAB = dict(minute='5', hour='*', day_of_month='*', month_of_year='*', day_of_week='*')


def _repoint(apps, from_task, to_task, to_name, to_description, to_crontab):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTasks = apps.get_model('django_celery_beat', 'PeriodicTasks')
    CrontabSchedule = apps.get_model('django_celery_beat', 'CrontabSchedule')
    entries = PeriodicTask.objects.filter(task=from_task)
    if not entries.exists():
        return
    if PeriodicTask.objects.filter(name=to_name).exists():
        entries.delete()
    else:
        crontab, _ = CrontabSchedule.objects.get_or_create(**to_crontab)
        entries.update(task=to_task, name=to_name, description=to_description, crontab=crontab)
    # tell the DatabaseScheduler its schedule changed, as PeriodicTask's signals would
    PeriodicTasks.objects.update_or_create(ident=1, defaults={'last_update': timezone.now()})


def forwards(apps, schema_editor):
    _repoint(apps, OLD_TASK, NEW_TASK, NEW_NAME, NEW_DESCRIPTION, NEW_CRONTAB)


def backwards(apps, schema_editor):
    _repoint(apps, NEW_TASK, OLD_TASK, OLD_NAME, OLD_DESCRIPTION, OLD_CRONTAB)


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0009_watermark'),
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
