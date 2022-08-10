import datetime
import pytest
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl import Search
from factories import EmailListFactory, ThreadFactory, MessageFactory

from mlarchive.archive.models import Message
from mlarchive.archive.backends.elasticsearch import ESBackend


@pytest.mark.django_db(transaction=True)
def test_clear_index(search_api_messages):
    index = settings.ELASTICSEARCH_INDEX_NAME
    client = ESBackend().client
    s = Search(using=client, index=index)
    assert s.count() > 0
    out = StringIO()
    call_command('clear_index', interactive=False, stdout=out)
    s = Search(using=client, index=index)
    assert s.count() == 0


@pytest.mark.django_db(transaction=True)
def test_rebuild_index(db_only):
    client = ESBackend().client
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 3
    info = client.cat.indices(settings.ELASTICSEARCH_INDEX_NAME)
    uuid = info.split()[3]
    # delete a record
    Message.objects.get(msgid='x001').delete()
    Message.objects.get(msgid='x002').delete()
    # add a record
    msg = Message.objects.get(msgid='x003')
    MessageFactory.create(email_list=msg.email_list,
                          thread=msg.thread,
                          thread_order=0,
                          msgid='x004',
                          date=datetime.datetime(2020, 1, 1))
    out = StringIO()
    call_command('rebuild_index', interactive=False, stdout=out)
    assert 'Indexing 2 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 2
    info = client.cat.indices(settings.ELASTICSEARCH_INDEX_NAME)
    new_uuid = info.split()[3]
    assert new_uuid != uuid
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    s = s.source(fields={'includes': ['msgid', 'id']})
    s = s.scan()
    index_msgids = [h['msgid'] for h in s]
    assert sorted(index_msgids) == ['x003', 'x004']


@pytest.mark.django_db(transaction=True)
def test_update_index(db_only):
    index = settings.ELASTICSEARCH_INDEX_NAME
    out = StringIO()
    call_command('clear_index', interactive=False, stdout=out)
    client = ESBackend().client
    s = Search(using=client, index=index)
    assert s.count() == 0
    out = StringIO()
    call_command('update_index', stdout=out)
    assert 'Indexing 3 Messages' in out.getvalue()
    s = Search(using=client, index=index)
    assert s.count() == 3

    msg = Message.objects.first()
    doc = client.get(index=index,
                     id='archive.message.{}'.format(msg.pk))
    assert doc['_source']['django_id'] == str(msg.pk)
    assert doc['_source']['text'] == 'This is a test message\nError reading message file'
    assert doc['_source']['email_list'] == 'public'
    assert doc['_source']['date'] == '2017-01-01T00:00:00'
    assert doc['_source']['frm'] == 'John Smith <john@example.com>'
    assert doc['_source']['msgid'] == 'x001'
    assert doc['_source']['subject'] == 'This is a test message'


@pytest.mark.django_db(transaction=True)
def test_update_index_date_range(db_only):
    index = settings.ELASTICSEARCH_INDEX_NAME
    out = StringIO()
    call_command('clear_index', interactive=False, stdout=out)
    client = ESBackend().client
    s = Search(using=client, index=index)
    assert s.count() == 0
    out = StringIO()
    call_command('update_index', 
                 start='2000-01-01T00:00:00',
                 end='2017-12-31T00:00:00',
                 stdout=out)
    assert 'Indexing 1 Messages' in out.getvalue()
    s = Search(using=client, index=index)
    assert s.count() == 1
    msg = Message.objects.get(msgid='x001')
    doc = client.get(index=index,
                     id='archive.message.{}'.format(msg.pk))
    assert doc['_source']['msgid'] == 'x001'


@pytest.mark.django_db(transaction=True)
def test_update_index_age(db_only):
    index = settings.ELASTICSEARCH_INDEX_NAME
    out = StringIO()
    call_command('clear_index', interactive=False, stdout=out)
    client = ESBackend().client
    s = Search(using=client, index=index)
    assert s.count() == 0
    out = StringIO()
    call_command('update_index', 
                 age='48',
                 stdout=out)
    assert 'Indexing 1 Messages' in out.getvalue()
    s = Search(using=client, index=index)
    assert s.count() == 1
    msg = Message.objects.get(msgid='x003')
    doc = client.get(index=index,
                     id='archive.message.{}'.format(msg.pk))
    assert doc['_source']['msgid'] == 'x003'


@pytest.mark.django_db(transaction=True)
def test_update_index_remove(db_only):
    client = ESBackend().client
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 3
    out = StringIO()
    msg = Message.objects.get(msgid='x003')
    pk = msg.pk
    msg.delete()
    call_command('update_index', 
                 remove=True,
                 stdout=out)
    assert 'Indexing 2 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 2
    with pytest.raises(NotFoundError) as excinfo:
        client.get(index=settings.ELASTICSEARCH_INDEX_NAME,
                   id='archive.message.{}'.format(pk))
        assert 'NotFoundError' in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_simple():
    pubone = EmailListFactory.create(name='pubone')
    athread = ThreadFactory.create(date=datetime.datetime(2013, 1, 1), email_list=pubone)
    MessageFactory.create(email_list=pubone,
                          frm='Björn',
                          thread=athread,
                          thread_order=0,
                          subject='Another message about RFC6759',
                          base_subject='Another message about RFC6759',
                          msgid='a01',
                          date=datetime.datetime(2013, 1, 1))
    assert Message.objects.all().count() == 1
