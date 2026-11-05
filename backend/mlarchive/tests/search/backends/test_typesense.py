import datetime
from copy import deepcopy
from types import SimpleNamespace

import pytest

from mlarchive.search.backends.typesense import (
    TypesenseSearchBackend,
    prepare_message,
)


TEST_COLLECTION = 'test-typesense'


@pytest.fixture
def backend(settings):
    """TypesenseSearchBackend bound to an isolated test collection.

    Monkey-patches settings.SEARCH_BACKENDS so the backend operates on a
    test-only collection that is torn down after each test. pytest-django's
    settings fixture restores the original value on exit.
    """
    backends = deepcopy(settings.SEARCH_BACKENDS)
    backends['default']['SCHEMA']['name'] = TEST_COLLECTION
    settings.SEARCH_BACKENDS = backends

    b = TypesenseSearchBackend()
    b.clear()  # start each test with a fresh, empty collection
    yield b
    try:
        b.client.collections[TEST_COLLECTION].delete()
    except Exception:
        pass


def make_doc(doc_id='1', subject='hello world', text='hello world body',
             email_list='public', frm_name='Alice'):
    return {
        'id': doc_id,
        'django_ct': 'archive.message',
        'django_id': int(doc_id),
        'date': 1700000000,
        'email_list': email_list,
        'frm': 'alice@example.com',
        'frm_name': frm_name,
        'msgid': f'msg-{doc_id}',
        'subject': subject,
        'subject_base': subject,
        'text': text,
        'thread_date': 1700000000,
        'thread_depth': 0,
        'thread_id': 1,
        'thread_order': 0,
        'spam_score': 0,
        'url': f'/arch/msg/public/{doc_id}/',
    }


def make_fake_message(pk=1, **overrides):
    defaults = dict(
        pk=pk,
        email_list=SimpleNamespace(name='public'),
        date=datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc),
        frm='alice <alice@example.com>',
        frm_name='Alice',
        msgid='x001',
        subject='Hello world',
        base_subject='Hello world',
        thread_date=datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc),
        thread_depth=0,
        thread_id=42,
        thread_order=0,
        spam_score=0,
        get_body=lambda: 'body content',
        get_absolute_url=lambda: '/arch/msg/public/x001/',
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# -------------------- setup --------------------

def test_setup_creates_collection(backend):
    info = backend.client.collections[TEST_COLLECTION].retrieve()
    assert info['name'] == TEST_COLLECTION
    assert len(info['fields']) == len(backend.schema['fields'])


def test_setup_is_idempotent(backend):
    backend.setup()
    backend.setup()
    info = backend.client.collections[TEST_COLLECTION].retrieve()
    assert info['name'] == TEST_COLLECTION


# -------------------- update --------------------

def test_update_indexes_document(backend):
    backend.update(make_doc(doc_id='1', subject='hello'))
    retrieved = backend.client.collections[TEST_COLLECTION].documents['1'].retrieve()
    assert retrieved['subject'] == 'hello'
    assert retrieved['email_list'] == 'public'


def test_update_upserts_existing_id(backend):
    backend.update(make_doc(doc_id='1', subject='first'))
    backend.update(make_doc(doc_id='1', subject='second'))
    retrieved = backend.client.collections[TEST_COLLECTION].documents['1'].retrieve()
    assert retrieved['subject'] == 'second'
    assert len(backend.search('*', limit=10)) == 1


def test_update_triggers_lazy_setup(settings):
    """Calling update() before setup() should create the collection."""
    backends = deepcopy(settings.SEARCH_BACKENDS)
    backends['default']['SCHEMA']['name'] = TEST_COLLECTION + '-lazy'
    settings.SEARCH_BACKENDS = backends

    b = TypesenseSearchBackend()
    try:
        b.client.collections[b.collection_name].delete()
    except Exception:
        pass

    assert not b.setup_complete
    b.update(make_doc(doc_id='1'))
    assert b.setup_complete
    # cleanup
    b.client.collections[b.collection_name].delete()


# -------------------- search --------------------

def test_search_returns_matching_hits(backend):
    backend.update(make_doc(doc_id='1', text='alpha body'))
    backend.update(make_doc(doc_id='2', text='beta body'))
    hits = backend.search('alpha')
    assert len(hits) == 1
    assert hits[0]['document']['id'] == '1'


def test_search_match_all(backend):
    for i in range(3):
        backend.update(make_doc(doc_id=str(i)))
    hits = backend.search('*', limit=10)
    assert len(hits) == 3


def test_search_respects_limit(backend):
    for i in range(5):
        backend.update(make_doc(doc_id=str(i)))
    hits = backend.search('*', limit=2)
    assert len(hits) == 2


def test_search_kwargs_override_query_by(backend):
    backend.update(make_doc(doc_id='1', subject='orangutan', text='elephant'))
    # Default query_by='text' — 'orangutan' is only in subject, so no match
    assert len(backend.search('orangutan')) == 0
    # Override query_by to search the subject field
    hits = backend.search('orangutan', query_by='subject')
    assert len(hits) == 1


def test_search_filter_by_kwarg(backend):
    backend.update(make_doc(doc_id='1', email_list='ietf'))
    backend.update(make_doc(doc_id='2', email_list='other'))
    hits = backend.search('*', filter_by='email_list:ietf')
    assert len(hits) == 1
    assert hits[0]['document']['email_list'] == 'ietf'


# -------------------- remove --------------------

def test_remove_deletes_document(backend):
    backend.update(make_doc(doc_id='1'))
    assert len(backend.search('*')) == 1
    backend.remove('1')
    assert len(backend.search('*')) == 0


def test_remove_missing_id_is_noop(backend):
    backend.remove('does-not-exist')  # must not raise


# -------------------- clear --------------------

def test_clear_empties_collection(backend):
    for i in range(3):
        backend.update(make_doc(doc_id=str(i)))
    assert len(backend.search('*')) == 3
    backend.clear()
    assert len(backend.search('*')) == 0
    # collection still exists (recreated empty)
    info = backend.client.collections[TEST_COLLECTION].retrieve()
    assert info['name'] == TEST_COLLECTION


def test_clear_when_collection_missing(backend):
    """clear() should also succeed if the collection has already been dropped."""
    backend.client.collections[TEST_COLLECTION].delete()
    backend.setup_complete = False
    backend.clear()
    info = backend.client.collections[TEST_COLLECTION].retrieve()
    assert info['name'] == TEST_COLLECTION


# -------------------- prepare_message --------------------

def test_prepare_message_shape():
    m = make_fake_message(pk=7)
    doc = prepare_message(m)
    assert doc['id'] == '7'
    assert doc['django_ct'] == 'archive.message'
    assert doc['django_id'] == 7
    assert doc['email_list'] == 'public'
    assert doc['msgid'] == 'x001'
    assert doc['subject'] == 'Hello world'
    assert doc['subject_base'] == 'Hello world'
    assert doc['url'] == '/arch/msg/public/x001/'
    # dates converted to epoch int64
    assert isinstance(doc['date'], int)
    assert isinstance(doc['thread_date'], int)
    assert doc['date'] == int(m.date.timestamp())
    # text is frm + subject + body joined with newlines
    assert doc['text'] == 'alice <alice@example.com>\nHello world\nbody content'


def test_prepare_message_round_trip_through_backend(backend):
    m = make_fake_message(pk=123, subject='unique-subject-token', msgid='xyz')
    backend.update(prepare_message(m))
    hits = backend.search('unique-subject-token', query_by='subject')
    assert len(hits) == 1
    doc = hits[0]['document']
    assert doc['id'] == '123'
    assert doc['msgid'] == 'xyz'
    assert doc['email_list'] == 'public'
