import datetime
import pytest
from datetime import timezone
from unittest.mock import patch

from django.db import transaction
from factories import EmailListFactory, ThreadFactory, MessageFactory

from mlarchive.archive import derived
from mlarchive.archive.derived import (ArtifactRef, MessageAdded,
    MessageMoved, Rebuild, MESSAGE_JSON, THREAD, MONTH_INDEX, message_json_ref, thread_ref, month_index_ref)


def dt(year, month, day):
    return datetime.datetime(year, month, day, tzinfo=timezone.utc)


@pytest.fixture()
def recorded():
    """Patch apply_and_purge and return the list of ref sets it was called with"""
    calls = []

    def record(refs):
        calls.append(set(refs))
        return []

    with patch('mlarchive.archive.derived.apply_and_purge', side_effect=record):
        yield calls


@pytest.fixture()
def two_threads():
    """A thread spanning Jan-Feb 2017, then a second thread in March, all
    in list 'public'. Returns (first, reply, other).
    """
    public = EmailListFactory.create(name='public', private=False)
    athread = ThreadFactory.create(date=dt(2017, 1, 1), email_list=public)
    bthread = ThreadFactory.create(date=dt(2017, 3, 1), email_list=public)
    first = MessageFactory.create(email_list=public, thread=athread, thread_order=0,
                                  date=dt(2017, 1, 1))
    reply = MessageFactory.create(email_list=public, thread=athread, thread_order=1,
                                  thread_depth=1, date=dt(2017, 2, 15))
    other = MessageFactory.create(email_list=public, thread=bthread, thread_order=0,
                                  date=dt(2017, 3, 1))
    return first, reply, other


# --------------------------------------------------
# Refs and dependency knowledge
# --------------------------------------------------

def test_artifact_ref_unknown_kind():
    with pytest.raises(ValueError):
        ArtifactRef('no_such_kind', 'x')


def test_serialize_round_trip():
    refs = {thread_ref(1), message_json_ref('public', 'abc=')}
    assert derived.deserialize_refs(derived.serialize_refs(refs)) == refs


@pytest.mark.django_db
def test_artifacts_for_message(two_threads):
    first, reply, other = two_threads
    assert derived.artifacts_for_message(reply) == {
        message_json_ref('public', reply.hashcode),
        thread_ref(reply.thread_id),
        month_index_ref('public', dt(2017, 2, 1)),
        # the thread is listed under the month of its first message
        month_index_ref('public', dt(2017, 1, 1)),
    }


@pytest.mark.django_db
def test_artifacts_for_list(two_threads):
    first, reply, other = two_threads
    refs = derived.artifacts_for_list(first.email_list)
    assert {r for r in refs if r.kind == MESSAGE_JSON} == {
        message_json_ref('public', m.hashcode) for m in two_threads}
    assert {r for r in refs if r.kind == THREAD} == {
        thread_ref(first.thread_id), thread_ref(other.thread_id)}
    assert {r.key for r in refs if r.kind == MONTH_INDEX} == {
        'public/2017-01', 'public/2017-02', 'public/2017-03'}


@pytest.mark.django_db
def test_touched_refs_message_added(two_threads):
    """A new message touches its whole thread and its list neighbors"""
    first, reply, other = two_threads
    refs = derived.touched_refs(MessageAdded(first.pk))
    # reply is both its thread sibling and the next message in list order
    assert {message_json_ref('public', m.hashcode) for m in (first, reply)} <= refs
    # every month the thread spans
    assert {'public/2017-01', 'public/2017-02'} <= {r.key for r in refs if r.kind == MONTH_INDEX}


@pytest.mark.django_db
def test_touched_refs_neighbor_threads(two_threads):
    """The list neighbors' threads are touched, so their pages are purged"""
    first, reply, other = two_threads
    refs = derived.touched_refs(MessageAdded(other.pk))
    assert thread_ref(other.thread_id) in refs
    # reply is the previous message in list order, in another thread
    assert thread_ref(reply.thread_id) in refs
    assert message_json_ref('public', reply.hashcode) in refs


@pytest.mark.django_db
def test_touched_refs_rebuild(two_threads):
    email_list = two_threads[0].email_list
    assert derived.touched_refs(Rebuild(email_list.pk)) == derived.artifacts_for_list(email_list)


@pytest.mark.django_db
def test_touched_refs_not_implemented(two_threads):
    first, reply, other = two_threads
    with pytest.raises(NotImplementedError):
        derived.touched_refs(MessageMoved(first.pk, source_list_id=first.email_list.pk))


# --------------------------------------------------
# Delivery
# --------------------------------------------------

@pytest.mark.django_db
def test_emit_applies_on_commit(two_threads, recorded, django_capture_on_commit_callbacks):
    first, reply, other = two_threads
    with django_capture_on_commit_callbacks() as callbacks:
        derived.emit(MessageAdded(first.pk))
    # TestCase never commits, so nothing is applied until the callback runs
    assert recorded == []
    assert len(callbacks) == 1
    callbacks[0]()
    assert recorded == [derived.touched_refs(MessageAdded(first.pk))]


@pytest.mark.django_db
def test_batch_flushes_union_once(two_threads, recorded, django_capture_on_commit_callbacks):
    first, reply, other = two_threads
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with derived.batch():
            derived.emit(MessageAdded(first.pk))
            with derived.batch():
                derived.emit(MessageAdded(other.pk))
            assert recorded == []
    assert len(callbacks) == 1
    expected = derived.touched_refs(MessageAdded(first.pk)).union(
        derived.touched_refs(MessageAdded(other.pk)))
    assert recorded == [expected]


@pytest.mark.django_db
def test_batch_flushes_when_block_raises(two_threads, recorded, django_capture_on_commit_callbacks):
    first, reply, other = two_threads
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with derived.batch():
                derived.emit(MessageAdded(first.pk))
                raise RuntimeError('boom')
    assert recorded == [derived.touched_refs(MessageAdded(first.pk))]


@pytest.mark.django_db(transaction=True)
def test_rolled_back_savepoint_is_not_applied(two_threads, recorded):
    first, reply, other = two_threads
    with transaction.atomic():
        derived.emit(MessageAdded(first.pk))
        try:
            with transaction.atomic():
                derived.emit(MessageAdded(other.pk))
                raise RuntimeError('roll back the savepoint')
        except RuntimeError:
            pass
        assert recorded == []
    assert recorded == [derived.touched_refs(MessageAdded(first.pk))]


@pytest.mark.django_db(transaction=True)
def test_rolled_back_transaction_is_not_applied(two_threads, recorded):
    first, reply, other = two_threads
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            derived.emit(MessageAdded(first.pk))
            raise RuntimeError('roll back')
    assert recorded == []


@pytest.mark.django_db(transaction=True)
def test_emit_autocommit_applies_immediately(two_threads, recorded):
    first, reply, other = two_threads
    derived.emit(MessageAdded(first.pk))
    assert len(recorded) == 1


@pytest.mark.django_db(transaction=True)
def test_flush_failure_is_logged_not_raised(two_threads, caplog):
    """The change is committed by the time _flush runs, so a failure, such as
    the broker being down, must not raise into the code that made it.
    """
    first, reply, other = two_threads
    with patch('mlarchive.archive.derived._flush', side_effect=RuntimeError('broker down')) as flush:
        # autocommit: runs at once
        derived.emit(MessageAdded(first.pk))
        # in a transaction: runs on commit
        with transaction.atomic():
            derived.emit(MessageAdded(other.pk))
        with derived.batch():
            derived.emit(MessageAdded(reply.pk))
    assert flush.call_count == 3
    assert 'broker down' in caplog.text


def test_flush_async_sends_chunks(settings):
    settings.DERIVED_ARTIFACTS_ASYNC = True
    refs = {thread_ref(n) for n in range(derived.TASK_CHUNK_SIZE + 1)}
    with patch('mlarchive.archive.tasks.apply_derived_artifacts_task.delay') as delay, \
            patch('mlarchive.archive.derived.apply_and_purge') as apply_and_purge:
        derived._flush(refs)
    sent = [derived.deserialize_refs(call.args[0]) for call in delay.call_args_list]
    assert [len(chunk) for chunk in sent] == [derived.TASK_CHUNK_SIZE, 1]
    assert set().union(*sent) == refs
    assert not apply_and_purge.called


def test_task_retries_failed_refs():
    """Only the refs that failed are retried, until they succeed"""
    from mlarchive.archive.tasks import apply_derived_artifacts_task
    good, bad = thread_ref(1), thread_ref(2)
    calls = []

    def flaky(refs):
        calls.append(set(refs))
        return [(bad, OSError('down'))] if len(calls) == 1 else []

    with patch('mlarchive.archive.derived.apply_and_purge', side_effect=flaky):
        apply_derived_artifacts_task.apply(args=(derived.serialize_refs([good, bad]),))
    assert calls == [{good, bad}, {bad}]


def test_task_gives_up_after_max_retries():
    from mlarchive.archive.tasks import apply_derived_artifacts_task, DERIVED_MAX_RETRIES
    bad = thread_ref(2)
    with patch('mlarchive.archive.derived.apply_and_purge',
               return_value=[(bad, OSError('down'))]) as apply_and_purge:
        result = apply_derived_artifacts_task.apply(args=(derived.serialize_refs([bad]),))
    assert result.successful()
    assert apply_and_purge.call_count == DERIVED_MAX_RETRIES + 1


# --------------------------------------------------
# Apply
# --------------------------------------------------

@pytest.mark.django_db
def test_build_message_json(two_threads):
    first, reply, other = two_threads
    with patch('mlarchive.archive.derived.store_message_json') as store, \
            patch('mlarchive.archive.derived.remove_from_storage') as remove:
        derived.build_message_json(f'public/{first.hashcode}')
        assert store.call_args.args[0] == first
        assert not remove.called


@pytest.mark.django_db
def test_build_message_json_missing_or_private(two_threads):
    first, reply, other = two_threads
    with patch('mlarchive.archive.derived.store_message_json') as store, \
            patch('mlarchive.archive.derived.remove_from_storage') as remove:
        derived.build_message_json('public/doesnotexist=')
        remove.assert_called_with(
            kind='ml-messages-json', name='public/doesnotexist', warn_if_missing=False)
        first.email_list.private = True
        first.email_list.save()
        derived.build_message_json(f'public/{first.hashcode}')
        remove.assert_called_with(
            kind='ml-messages-json', name=first.get_blob_name(), warn_if_missing=False)
        assert not store.called


@pytest.mark.django_db
def test_apply_failures(two_threads):
    first, reply, other = two_threads
    refs = {message_json_ref('public', first.hashcode), thread_ref(first.thread_id)}
    with patch('mlarchive.archive.derived.store_message_json', side_effect=OSError('down')):
        failures = derived.apply(refs)
        assert [ref for ref, _ in failures] == [message_json_ref('public', first.hashcode)]


# --------------------------------------------------
# Legacy purge
# --------------------------------------------------

@pytest.mark.django_db
def test_legacy_purge_targets(two_threads):
    first, reply, other = two_threads
    host = 'https://mailarchive.ietf.org'
    tags, urls = derived.legacy_purge_targets({
        thread_ref(first.thread_id),
        message_json_ref('public', first.hashcode),
        month_index_ref('public', dt(2017, 2, 1)),
    })
    assert tags == [first.get_cache_tag()]
    # 2017 has fewer than STATIC_INDEX_YEAR_MINIMUM messages, so is served as a year page
    assert urls == sorted([
        host + '/arch/browse/static/public/2017/',
        host + '/arch/browse/static/public/thread/2017/'])
    assert set(reply.get_absolute_static_index_urls()) <= set(urls)


@pytest.mark.django_db
def test_legacy_purge_targets_month_pages(two_threads, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 1
    first, reply, other = two_threads
    tags, urls = derived.legacy_purge_targets(derived.touched_refs(MessageAdded(reply.pk)))
    for message in (first, reply, other):
        assert message.get_cache_tag() in tags
    assert set(reply.get_absolute_static_index_urls()) <= set(urls)


@pytest.mark.django_db
def test_legacy_purge_chunks(two_threads, settings):
    settings.SERVER_MODE = 'production'
    settings.USING_CDN = True
    refs = {thread_ref(n) for n in range(derived.PURGE_CHUNK_SIZE + 1)}
    with patch('mlarchive.archive.derived.Cloudflare') as cloudflare:
        derived.legacy_purge(refs)
    purge = cloudflare.return_value.__enter__.return_value.cache.purge
    assert [len(call.kwargs['tags']) for call in purge.call_args_list] == [derived.PURGE_CHUNK_SIZE, 1]


def test_task_acks_late():
    from mlarchive.archive.tasks import apply_derived_artifacts_task
    assert apply_derived_artifacts_task.acks_late
