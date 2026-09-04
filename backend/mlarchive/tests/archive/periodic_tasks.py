# Copyright The IETF Trust 2026, All Rights Reserved
import json

import pytest
from django.core.management import call_command
from django_celery_beat.models import PeriodicTask


@pytest.mark.django_db
def test_create_default_tasks_is_idempotent_and_disabled():
    call_command('periodic_tasks', '--create-default')
    call_command('periodic_tasks', '--create-default')

    tasks = PeriodicTask.objects.filter(task__startswith='mlarchive.archive.tasks.')
    assert tasks.count() == 5
    assert not tasks.filter(enabled=True).exists()

    reconcile = tasks.get(task='mlarchive.archive.tasks.reconcile_stored_objects_task')
    assert reconcile.crontab.day_of_week == '0'
    assert json.loads(reconcile.kwargs) == {'repair': True}
