import datetime
from types import SimpleNamespace

import pytest

from mlarchive.search.backends.elasticsearch import (
    ElasticSearchBackend,
    full_prepare,
    prep_text,
    get_identifier,
)


TEST_INDEX = 'test-elasticsearch'


@pytest.fixture
def backend(settings):
    """ElasticSearchBackend bound to an isolated test index.

    Monkey-patches settings.ELASTICSEARCH_CONNECTION so the backend operates
    on a test-only index that is torn down after each test. pytest-django's
    settings fixture restores the original value on exit.
    """
    connection = dict(settings.ELASTICSEARCH_CONNECTION)
    connection['INDEX_NAME'] = TEST_INDEX
    settings.ELASTICSEARCH_CONNECTION = connection

    b = ElasticSearchBackend()
    b.client.indices.delete(index=TEST_INDEX, ignore=404)
    b.setup()
    yield b
    try:
        b.client.indices.delete(index=TEST_INDEX, ignore=404)
    except Exception:
        pass


def make_fake_message(pk=1, **overrides):
    defaults = dict(
        pk=pk,
        django_id=str(pk),
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


def _doc_id(pk):
    return 'archive.message.{}'.format(pk)


def _count(backend):
    backend.client.indices.refresh(index=TEST_INDEX)
    return backend.client.count(index=TEST_INDEX)['count']


# -------------------- setup --------------------

def test_setup_creates_index(backend):
    assert backend.client.indices.exists(index=TEST_INDEX)
    mapping = backend.client.indices.get_mapping(index=TEST_INDEX)
    props = mapping[TEST_INDEX]['mappings']['properties']
    assert 'subject' in props
    assert 'email_list' in props


def test_setup_is_idempotent(backend):
    backend.setup()
    backend.setup()
    assert backend.client.indices.exists(index=TEST_INDEX)


def test_setup_sets_complete_flag(backend):
    assert backend.setup_complete is True


# -------------------- update --------------------

def test_update_indexes_document(backend):
    m = make_fake_message(pk=1, subject='hello')
    backend.update(full_prepare(m))
    doc = backend.client.get(index=TEST_INDEX, id=_doc_id(1))
    assert doc['_source']['subject'] == 'hello'
    assert doc['_source']['email_list'] == 'public'
    assert doc['_source']['django_id'] == '1'


def test_update_upserts_existing_id(backend):
    backend.update(full_prepare(make_fake_message(pk=1, subject='first')))
    backend.update(full_prepare(make_fake_message(pk=1, subject='second')))
    doc = backend.client.get(index=TEST_INDEX, id=_doc_id(1))
    assert doc['_source']['subject'] == 'second'
    assert _count(backend) == 1


def test_bulk_update_indexes_multiple(backend):
    msgs = [make_fake_message(pk=i, subject='s{}'.format(i)) for i in range(1, 4)]
    backend.bulk_update(full_prepare(m) for m in msgs)
    assert _count(backend) == 3


def test_update_triggers_lazy_setup(settings):
    """Calling update() before setup() should create the index."""
    connection = dict(settings.ELASTICSEARCH_CONNECTION)
    connection['INDEX_NAME'] = TEST_INDEX + '-lazy'
    settings.ELASTICSEARCH_CONNECTION = connection

    b = ElasticSearchBackend()
    b.client.indices.delete(index=b.index_name, ignore=404)
    try:
        assert not b.setup_complete
        b.update(full_prepare(make_fake_message(pk=1)))
        assert b.setup_complete
        assert b.client.indices.exists(index=b.index_name)
    finally:
        b.client.indices.delete(index=b.index_name, ignore=404)


# -------------------- remove --------------------

def test_remove_deletes_document_by_string(backend):
    backend.update(full_prepare(make_fake_message(pk=1)))
    assert _count(backend) == 1
    backend.remove(_doc_id(1))
    assert _count(backend) == 0


def test_remove_deletes_document_by_object(backend):
    m = make_fake_message(pk=1)
    backend.update(full_prepare(m))
    assert _count(backend) == 1

    model_meta = SimpleNamespace(
        app_label='archive',
        model_name='message',
        concrete_model=None,
    )
    model_meta.concrete_model = SimpleNamespace(_meta=model_meta)
    obj = SimpleNamespace(_meta=model_meta, _get_pk_val=lambda: 1)
    backend.remove(obj)
    assert _count(backend) == 0


def test_remove_missing_id_is_noop(backend):
    backend.remove(_doc_id(9999))  # must not raise


def test_remove_invalid_identifier_string_raises(backend):
    with pytest.raises(AttributeError):
        backend.remove('not a valid identifier!')


# -------------------- clear --------------------

def test_clear_empties_index(backend):
    for i in range(1, 4):
        backend.update(full_prepare(make_fake_message(pk=i)))
    assert _count(backend) == 3
    backend.clear()
    assert _count(backend) == 0
    # index still exists (recreated empty)
    assert backend.client.indices.exists(index=TEST_INDEX)


def test_clear_when_index_missing(backend):
    """clear() should also succeed if the index has already been dropped."""
    backend.client.indices.delete(index=TEST_INDEX, ignore=404)
    backend.setup_complete = False
    backend.clear()
    assert backend.client.indices.exists(index=TEST_INDEX)


# -------------------- prep_text --------------------

def test_prep_text_joins_fields():
    m = make_fake_message()
    text = prep_text(m)
    assert text == 'alice <alice@example.com>\nHello world\nbody content'


# -------------------- full_prepare --------------------

def test_full_prepare_shape():
    m = make_fake_message(pk=7)
    doc = full_prepare(m)
    assert doc['id'] == 'archive.message.7'
    assert doc['django_ct'] == 'archive.message'
    assert doc['django_id'] == '7'
    assert doc['email_list'] == 'public'
    assert doc['email_list_exact'] == 'public'
    assert doc['frm_name'] == 'Alice'
    assert doc['frm_name_exact'] == 'Alice'
    assert doc['msgid'] == 'x001'
    assert doc['subject'] == 'Hello world'
    assert doc['subject_base'] == 'Hello world'
    assert doc['url'] == '/arch/msg/public/x001/'
    # dates are isoformat strings
    assert doc['date'] == m.date.isoformat()
    # text is frm + subject + body joined with newlines
    assert doc['text'] == 'alice <alice@example.com>\nHello world\nbody content'


def test_full_prepare_round_trip_through_backend(backend):
    m = make_fake_message(pk=123, subject='unique-subject-token', msgid='xyz')
    backend.update(full_prepare(m))
    doc = backend.client.get(index=TEST_INDEX, id=_doc_id(123))
    assert doc['_source']['msgid'] == 'xyz'
    assert doc['_source']['subject'] == 'unique-subject-token'
    assert doc['_source']['django_id'] == '123'
    assert doc['_source']['email_list'] == 'public'


# -------------------- get_identifier --------------------

def test_get_identifier_accepts_valid_string():
    assert get_identifier('archive.message.42') == 'archive.message.42'


def test_get_identifier_rejects_invalid_string():
    with pytest.raises(AttributeError):
        get_identifier('not-valid')


def test_get_identifier_from_object():
    model_meta = SimpleNamespace(
        app_label='archive',
        model_name='message',
        concrete_model=None,
    )
    model_meta.concrete_model = SimpleNamespace(_meta=model_meta)
    obj = SimpleNamespace(_meta=model_meta, _get_pk_val=lambda: 99)
    assert get_identifier(obj) == 'archive.message.99'
