import datetime
import mailbox
import pytest
import requests
from factories import EmailListFactory, UserFactory
from mock import patch
import os
import subprocess   # noqa
import xml.etree.ElementTree as ET

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import AnonymousUser
from mlarchive.archive.utils import (get_noauth, get_lists, get_lists_for_user,
    lookup_user, process_members, get_membership, check_inactive, EmailList,
    create_mbox_file, _get_lists_as_xml, get_subscribers, Subscriber,
    get_known_mailman_lists, get_subscriber_count,
    get_mailman_lists, get_membership_3, get_subscriber_counts)
from mlarchive.archive.models import User
from factories import EmailListFactory

# --------------------------------------------------
# Helper Classes
# --------------------------------------------------


class MailmanList:
    def __init__(self, list_name, member_count):
        self.list_name = list_name
        self.member_count = member_count


class ListResponse:
    def __init__(self, lists):
        self.lists = lists


# --------------------------------------------------
# Tests
# --------------------------------------------------


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
    # setup mocks
    response1 = requests.Response()
    response1.status_code = 404
    response2 = requests.Response()
    response2.status_code = 200
    response2._content = b'{"person.person": {"1": {"user": ""}}}'
    response3 = requests.Response()
    response3.status_code = 200
    response3._content = b'{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    mock_post.side_effect = [response1, response2, response3]
    # test error status
    user = lookup_user('joe@example.com')
    assert user is None
    # test no user object
    user = lookup_user('joe@example.com')
    assert user is None
    # test success
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


@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_process_members_case_insensitive(mock_post):
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"person.person": {"1": {"user": {"username": "Joe@example.com"}}}}'
    mock_post.return_value = response
    email_list = EmailListFactory.create(name='private', private=True)
    user = User.objects.create(username='joe@example.com')
    email_list.members.add(user)
    assert email_list.members.count() == 1
    process_members(email_list, ['Joe@example.com'])
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


@patch('mailmanclient.restbase.connection.Connection.call')
@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_get_membership_3(mock_post, mock_client):
    # setup
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    if os.path.exists(path):
        os.remove(path)

    private = EmailListFactory.create(name='bee', private=True)
    
    # prep mock
    response_members = requests.Response()
    response_members.status_code = 200
    response_members._content = b'{"start": 0, "total_size": 1, "entries": [{"address": "http://172.19.199.3:8001/3.1/addresses/bperson@example.com", "bounce_score": 0, "last_warning_sent": "0001-01-01T00:00:00", "total_warnings_sent": 0, "delivery_mode": "regular", "email": "bperson@example.com", "list_id": "bee.ietf.org", "subscription_mode": "as_address", "role": "member", "user": "http://172.19.199.3:8001/3.1/users/bb94f3e8ee504f788aaee97d0b76c3d1", "display_name": "Bart Person", "self_link": "http://172.19.199.3:8001/3.1/members/a963ef52752e4f679ee3fe8253208690", "member_id": "a963ef52752e4f679ee3fe8253208690", "http_etag": "\\"36b75489a29b268a1cf7a08c1c6d9a54f72b1c1e\\""}], "http_etag": "\\"a613273c96620e5eea18627b9c7dd4b50a23be8d\\""}'

    response_lookup = requests.Response()
    response_lookup.status_code = 200
    response_lookup._content = b'{"person.person": {"1": {"user": {"username": "bperson@example.com"}}}}'
        
    mock_client.return_value = response_members, response_members.json()
    mock_post.return_value = response_lookup
    assert private.members.count() == 0
    get_membership_3(quiet=True)
    assert private.members.count() == 1
    assert private.members.first().username == 'bperson@example.com'
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
def test_get_lists_as_xml(client):
    private = EmailListFactory.create(name='private', private=True)
    EmailListFactory.create(name='public', private=False)
    user = UserFactory.create(username='test')
    private.members.add(user)
    xml = _get_lists_as_xml()
    root = ET.fromstring(xml)

    print(xml)

    public_anonymous = root.find("shared_root/[@name='public']").find("user/[@name='anonymous']")
    assert public_anonymous.attrib['access'] == 'read'

    private_anonymous = root.find("shared_root/[@name='private']").find("user/[@name='anonymous']")
    assert private_anonymous.attrib['access'] == 'none'

    private_test = root.find("shared_root/[@name='private']").find("user/[@name='test']")
    assert private_test.attrib['access'] == 'read,write'


@patch('subprocess.check_output')
@pytest.mark.django_db(transaction=True)
def test_get_subscribers(mock_output):
    public = EmailListFactory.create(name='public')
    # handle multiple calls to check_output
    mock_output.return_value = b'joe@example.com\nfred@example.com\n'
    subs = get_subscribers('public')
    assert subs == ['joe@example.com', 'fred@example.com']


@patch('subprocess.check_output')
@pytest.mark.django_db(transaction=True)
def test_get_subscriber_count(mock_output):
    public = EmailListFactory.create(name='public')

    # handle multiple calls to check_output
    mock_output.side_effect = [
        b'     public - Public List\n     private - Private List',
        b'joe@example.com\nfred@example.com\nmary@example.com\n',
    ]
    assert Subscriber.objects.count() == 0
    get_subscriber_count()
    subscriber = Subscriber.objects.first()
    assert subscriber.email_list == public
    assert subscriber.date == datetime.date.today()
    assert subscriber.count == 3


@patch('mailmanclient.client.Client.get_lists')
@pytest.mark.django_db(transaction=True)
def test_get_subscriber_counts(mock_client):
    mock_client.return_value = [MailmanList(list_name='bee', member_count=1)]
    public = EmailListFactory.create(name='bee')
    assert Subscriber.objects.count() == 0
    get_subscriber_counts()
    subscriber = Subscriber.objects.first()
    assert subscriber.email_list == public
    assert subscriber.date == datetime.date.today()
    assert subscriber.count == 1


@patch('subprocess.check_output')
@pytest.mark.django_db(transaction=True)
def test_get_known_mailman_lists(mock_output):
    public = EmailListFactory.create(name='public')
    private = EmailListFactory.create(name='private', private=True)
    mock_output.return_value = b'    public - Public Email List\n   private - Private Email List'
    mlists = get_known_mailman_lists(private=True)
    assert len(mlists) == 1
    assert list(mlists) == [private]


@patch('mailmanclient.restbase.connection.Connection.call')
@pytest.mark.django_db(transaction=True)
def test_get_mailman_lists(mock_client):
    ant = EmailListFactory.create(name='ant')
    bee = EmailListFactory.create(name='bee', private=True)
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"start": 0, "total_size": 2, "entries": [{"advertised": true, "display_name": "Ant", "fqdn_listname": "ant@lists.example.com", "list_id": "ant.lists.example.com", "list_name": "ant", "mail_host": "lists.example.com", "member_count": 0, "volume": 1, "description": "", "self_link": "http://172.19.199.3:8001/3.1/lists/ant.lists.example.com", "http_etag": "cb67744198a68efb427c24fab35d9fc593186d6c"}, {"advertised": true, "display_name": "Bee", "fqdn_listname": "bee@lists.example.com", "list_id": "bee.lists.example.com", "list_name": "bee", "mail_host": "lists.example.com", "member_count": 1, "volume": 1, "description": "", "self_link": "http://172.19.199.3:8001/3.1/lists/bee.lists.example.com", "http_etag": "fb6d81b0f573936532b0b02d4d2116023a9e56a8"}], "http_etag": "ef59c8ea7baa670940fd87f99fce83ba5013381f"}'
    mock_client.return_value = response, response.json()
    mlists = get_mailman_lists(private=True)
    assert len(mlists) == 1
    assert list(mlists) == [bee]
