# Copyright The IETF Trust 2026, All Rights Reserved
import datetime
import json

import pytest
from factories import EmailListFactory, MessageFactory
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage_utils import get_metadata, retrieve_bytes
from mlarchive.archive.tasks import (
    BLOBDB_QUEUE, REBUILD_JSON_STOP_KEY, rebuild_messages_json)


@pytest.fixture
def real_cache():
    """The test settings use DummyCache, which cannot hold the task's stop flag."""
    locmem = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    with override_settings(CACHES=locmem):
        cache.clear()
        yield
        cache.clear()


@pytest.fixture
def idle_queue():
    """Pretend the blobdb queue is empty so the task does not wait."""
    with patch('mlarchive.archive.tasks.queue_depth', return_value=0) as depth:
        yield depth


def chain_kwargs(**overrides):
    kwargs = dict(
        start_after_pk=0, batch_size=1000, start_date=None, end_date=None,
        email_lists=None, countdown=30, max_queue_depth=100)
    kwargs.update(overrides)
    return kwargs


@pytest.mark.django_db(transaction=True)
def test_rebuild_writes_public_json_through_the_storage(idle_queue):
    """Every rewritten object is indexed and carries the batch-computed nav links."""
    public = EmailListFactory.create(name='rebuild')
    private = EmailListFactory.create(name='secret', private=True)
    # distinct dates, so the list navigation between the two is well defined
    when = datetime.datetime(2026, 5, 1, 12, 0, tzinfo=datetime.timezone.utc)
    first = MessageFactory.create(email_list=public, date=when)
    second = MessageFactory.create(email_list=public, date=when + datetime.timedelta(hours=1))
    hidden = MessageFactory.create(email_list=private)

    with patch.object(rebuild_messages_json, 'apply_async') as apply_async:
        rebuild_messages_json(batch_size=10, countdown=5)

    for message in (first, second):
        data = json.loads(retrieve_bytes('ml-messages-json', message.get_blob_name()))
        assert data['hashcode'] == message.hashcode
        metadata = get_metadata('ml-messages-json', message.get_blob_name())
        assert metadata is not None and metadata.len > 0
    assert json.loads(retrieve_bytes('ml-messages-json', first.get_blob_name()))['next_in_list'] \
        == second.get_absolute_url()
    assert get_metadata('ml-messages-json', hidden.get_blob_name()) is None

    apply_async.assert_called_once_with(
        kwargs=chain_kwargs(start_after_pk=hidden.pk, batch_size=10, countdown=5),
        countdown=5, queue=BLOBDB_QUEUE)


@pytest.mark.django_db(transaction=True)
def test_rebuild_overwrites_existing_json(idle_queue):
    public = EmailListFactory.create(name='rebuild')
    message = MessageFactory.create(email_list=public)
    with patch.object(rebuild_messages_json, 'apply_async'):
        rebuild_messages_json()
    before = get_metadata('ml-messages-json', message.get_blob_name())

    message.subject = 'A different subject'
    message.save()
    with patch.object(rebuild_messages_json, 'apply_async'):
        rebuild_messages_json()

    after = get_metadata('ml-messages-json', message.get_blob_name())
    assert after.sha384 != before.sha384
    assert StoredObject.objects.filter(store='ml-messages-json').count() == 1


@pytest.mark.django_db
def test_rebuild_waits_while_queue_is_busy():
    public = EmailListFactory.create(name='rebuild')
    MessageFactory.create(email_list=public)

    with patch('mlarchive.archive.tasks.queue_depth', return_value=101), \
            patch.object(rebuild_messages_json, 'apply_async') as apply_async:
        rebuild_messages_json(start_after_pk=7, countdown=12, max_queue_depth=100)

    assert not StoredObject.objects.filter(store='ml-messages-json').exists()
    apply_async.assert_called_once_with(
        kwargs=chain_kwargs(start_after_pk=7, countdown=12), countdown=12, queue=BLOBDB_QUEUE)


@pytest.mark.django_db
def test_rebuild_completion_reconciles_the_bucket(idle_queue):
    with patch('mlarchive.archive.tasks.reconcile_bucket', return_value={'rows': 0}) as reconcile, \
            patch.object(rebuild_messages_json, 'apply_async') as apply_async:
        rebuild_messages_json(start_after_pk=0)

    reconcile.assert_called_once_with('ml-messages-json')
    apply_async.assert_not_called()


@pytest.mark.django_db
def test_rebuild_honours_stop_flag(real_cache, idle_queue):
    public = EmailListFactory.create(name='rebuild')
    MessageFactory.create(email_list=public)
    cache.set(REBUILD_JSON_STOP_KEY, True, timeout=None)

    with patch.object(rebuild_messages_json, 'apply_async') as apply_async:
        rebuild_messages_json()

    idle_queue.assert_not_called()
    apply_async.assert_not_called()
    assert not StoredObject.objects.filter(store='ml-messages-json').exists()


@pytest.mark.django_db(transaction=True)
def test_rebuild_continues_past_a_failing_message(idle_queue, caplog):
    public = EmailListFactory.create(name='rebuild')
    bad = MessageFactory.create(email_list=public)
    good = MessageFactory.create(email_list=public)
    real_store = rebuild_messages_json.__wrapped__.__globals__['store_message_json']

    def flaky(message, nav=None):
        if message.pk == bad.pk:
            raise RuntimeError('cannot serialise')
        return real_store(message, nav=nav)

    with patch('mlarchive.archive.tasks.store_message_json', side_effect=flaky), \
            patch.object(rebuild_messages_json, 'apply_async') as apply_async:
        rebuild_messages_json()

    assert get_metadata('ml-messages-json', bad.get_blob_name()) is None
    assert get_metadata('ml-messages-json', good.get_blob_name()) is not None
    assert f'failed to write {bad.get_blob_name()}' in caplog.text
    apply_async.assert_called_once()
