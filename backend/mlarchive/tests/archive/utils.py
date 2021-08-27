from __future__ import absolute_import, division, print_function, unicode_literals

from io import StringIO
import datetime
import mailbox
import pytest
import requests
from factories import EmailListFactory, UserFactory
from mock import patch
import os
import subprocess   # noqa


from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl import Search

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.contrib.auth.models import AnonymousUser
from mlarchive.archive.utils import (get_noauth, get_lists, get_lists_for_user,
    lookup_user, process_members, get_membership, check_inactive, EmailList,
    create_mbox_file, ESBackend)
from mlarchive.archive.models import Message
from factories import EmailListFactory, ThreadFactory, MessageFactory

from mlarchive.archive.management.commands.update_index_new import Command


@pytest.mark.django_db(transaction=True)
def test_get_noauth():
    user = UserFactory.create(username='noauth')
    EmailListFactory.create(name='public')
    private1 = EmailListFactory.create(name='private1', private=True)
    EmailListFactory.create(name='private2', private=True)
    private1.members.add(user)
    lists = get_noauth(user)
    assert len(lists) == 1
    assert lists == ['private2']


@pytest.mark.django_db(transaction=True)
def test_get_noauth_updates(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    user = UserFactory.create(username='noauth')
    public = EmailListFactory.create(name='public')
    private = EmailListFactory.create(name='private', private=True)
    private.members.add(user)

    if user.is_anonymous:
        user_id = 0
    else:
        user_id = user.id

    key = '{:04d}-noauth'.format(user_id)
    print("key {}:{}".format(key, cache.get(key)))
    assert 'public' not in get_noauth(user)
    print("key {}:{}".format(key, cache.get(key)))
    # assert cache.get(key) == []
    public.private = True
    public.save()
    assert 'public' in get_noauth(user)
    print("key {}:{}".format(key, cache.get(key)))
    # assert False


@pytest.mark.django_db(transaction=True)
def test_get_lists():
    EmailListFactory.create(name='pubone')
    assert 'pubone' in get_lists()


@pytest.mark.django_db(transaction=True)
def test_get_lists_for_user(admin_user):
    EmailListFactory.create(name='public')
    private1 = EmailListFactory.create(name='private1', private=True)
    private2 = EmailListFactory.create(name='private2', private=True)
    user1 = UserFactory.create(username='user1')
    private1.members.add(user1)
    anonymous = AnonymousUser()
    print(anonymous.is_authenticated)
    print(EmailList.objects.filter(private=False).count())
    assert len(get_lists_for_user(admin_user)) == 3
    assert len(get_lists_for_user(anonymous)) == 1
    lists = get_lists_for_user(user1)
    assert private1.name in lists
    assert private2.name not in lists


@patch('requests.post')
def test_lookup_user(mock_post):
    response = requests.Response()
    # test error status
    response.status_code = 404
    mock_post.return_value = response
    user = lookup_user('joe@example.com')
    assert user is None
    # test no user object
    response.status_code = 200
    response._content = b'{"person.person": {"1": {"user": ""}}}'
    user = lookup_user('joe@example.com')
    assert user is None
    # test success
    response._content = b'{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    user = lookup_user('joe@example.com')
    assert user == 'joe@example.com'


@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_process_members(mock_post):
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    mock_post.return_value = response
    email_list = EmailListFactory.create(name='private', private=True)
    assert email_list.members.count() == 0
    process_members(email_list, ['joe@example.com'])
    assert email_list.members.count() == 1
    assert email_list.members.get(username='joe@example.com')


@patch('subprocess.check_output')
@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_get_membership(mock_post, mock_output):
    # setup
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    if os.path.exists(path):
        os.remove(path)

    private = EmailListFactory.create(name='private', private=True)
    # handle multiple calls to check_output
    mock_output.side_effect = [b'private - Private Email List', b'joe@example.com']
    response = requests.Response()
    mock_post.return_value = response
    response.status_code = 200
    response._content = b'{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    assert private.members.count() == 0
    options = DummyOptions()
    options.quiet = True
    get_membership(options, None)
    assert private.members.count() == 1
    assert private.members.first().username == 'joe@example.com'
    assert os.path.exists(path)


class DummyOptions(object):
    pass


@patch('mlarchive.archive.utils.input')
@patch('subprocess.check_output')
@pytest.mark.django_db(transaction=True)
def test_check_inactive(mock_output, mock_input):
    mock_input.return_value = 'n'
    EmailListFactory.create(name='public')
    EmailListFactory.create(name='acme')
    support = EmailListFactory.create(name='support')

    # handle multiple calls to check_output
    mock_output.side_effect = [
        'public - Public Email List',
        'acme-arch:  "|/usr/home/call-archives.py acme"',
        'public - Public Email List',
        'acme-arch:  "|/usr/home/call-archives.py acme"',
    ]
    assert EmailList.objects.filter(active=True).count() == 3

    check_inactive(prompt=True)
    assert EmailList.objects.filter(active=True).count() == 3

    check_inactive(prompt=False)
    assert EmailList.objects.filter(active=True).count() == 2
    assert EmailList.objects.filter(active=False).first() == support


@pytest.mark.django_db(transaction=True)
def test_create_mbox_file(tmpdir, settings, latin1_messages):
    print('tmpdir: {}'.format(tmpdir))
    settings.ARCHIVE_MBOX_DIR = str(tmpdir)
    elist = EmailList.objects.get(name='acme')    
    first_message = elist.message_set.first()
    month = first_message.date.month
    year = first_message.date.year
    create_mbox_file(month=month, year=year, elist=elist)
    path = os.path.join(settings.ARCHIVE_MBOX_DIR, 'public', elist.name, '{}-{:02d}.mail'.format(year, month))
    assert os.path.exists(path)
    mbox = mailbox.mbox(path)
    assert len(mbox) == 1
    mbox.close()


@pytest.mark.django_db(transaction=True)
def test_clear_index(search_api_messages):
    client = Elasticsearch()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() > 0
    out = StringIO()
    call_command('clear_index_new', interactive=False, stdout=out)
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 0


@pytest.mark.django_db(transaction=True)
def test_rebuild_index(db_only):
    client = Elasticsearch()
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
    call_command('rebuild_index_new', interactive=False, stdout=out)
    assert 'Indexing 2 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 2
    info = client.cat.indices(settings.ELASTICSEARCH_INDEX_NAME)
    new_uuid = info.split()[3]
    assert new_uuid != uuid
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    s = s.source(fields={'includes': ['django_id', 'id']})
    s = s.scan()
    index_pks = [h['django_id'] for h in s]
    assert sorted(index_pks) == ['3', '4']


@pytest.mark.django_db(transaction=True)
def test_update_index(db_only):
    out = StringIO()
    call_command('clear_index_new', interactive=False, stdout=out)
    client = Elasticsearch()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 0
    out = StringIO()
    call_command('update_index_new', stdout=out)
    assert 'Indexing 3 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 3

    doc = client.get(index=settings.ELASTICSEARCH_INDEX_NAME,
                     doc_type='modelresult',
                     id='archive.message.1')
    assert doc['_source']['django_id'] == '1'
    assert doc['_source']['text'] == 'This is a test message\nError reading message file'
    assert doc['_source']['email_list'] == 'public'
    assert doc['_source']['date'] == '2017-01-01T00:00:00'
    assert doc['_source']['frm'] == 'John Smith <john@example.com>'
    assert doc['_source']['msgid'] == 'x001'
    assert doc['_source']['subject'] == 'This is a test message'


@pytest.mark.django_db(transaction=True)
def test_update_index_date_range(db_only):
    out = StringIO()
    call_command('clear_index_new', interactive=False, stdout=out)
    client = Elasticsearch()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 0
    out = StringIO()
    call_command('update_index_new', 
                 start='2000-01-01T00:00:00',
                 end='2017-12-31T00:00:00',
                 stdout=out)
    assert 'Indexing 1 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 1
    doc = client.get(index=settings.ELASTICSEARCH_INDEX_NAME,
                     doc_type='modelresult',
                     id='archive.message.1')
    assert doc['_source']['msgid'] == 'x001'


@pytest.mark.django_db(transaction=True)
def test_update_index_age(db_only):
    out = StringIO()
    call_command('clear_index_new', interactive=False, stdout=out)
    client = Elasticsearch()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 0
    out = StringIO()
    call_command('update_index_new', 
                 age='48',
                 stdout=out)
    assert 'Indexing 1 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 1
    doc = client.get(index=settings.ELASTICSEARCH_INDEX_NAME,
                     doc_type='modelresult',
                     id='archive.message.3')
    assert doc['_source']['msgid'] == 'x003'


@pytest.mark.django_db(transaction=True)
def test_update_index_remove(db_only):
    client = Elasticsearch()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 3
    out = StringIO()
    Message.objects.get(msgid='x003').delete()
    call_command('update_index_new', 
                 remove=True,
                 stdout=out)
    assert 'Indexing 2 Messages' in out.getvalue()
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    assert s.count() == 2
    with pytest.raises(NotFoundError) as excinfo:
        client.get(index=settings.ELASTICSEARCH_INDEX_NAME,
                   doc_type='modelresult',
                   id='archive.message.3')
        assert 'NotFoundError' in str(excinfo.value)
