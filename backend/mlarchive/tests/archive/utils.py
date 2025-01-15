import datetime
import json
import mailbox
import pytest
import requests
from factories import EmailListFactory, UserFactory
from mock import patch
import os
import subprocess   # noqa
import time
import xml.etree.ElementTree as ET

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import AnonymousUser
from django.http import QueryDict
from mlarchive.archive.utils import (get_noauth, get_lists, get_lists_for_user,
    lookup_user, process_members, check_inactive, EmailList, purge_incoming,
    create_mbox_file, _get_lists_as_xml, get_subscribers, Subscriber,
    get_mailman_lists, get_membership_3, get_subscriber_counts, get_fqdn,
    update_mbox_files, _export_lists, move_list)
from mlarchive.archive.models import User, Message, Redirect
from mlarchive.archive.mail import make_hash
from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.backends.elasticsearch import search_from_form
from factories import EmailListFactory


MAILMAN_LIST_PUBLIC = {
    "advertised": True,
    "display_name": "public",
    "fqdn_listname": "public@example.com",
    "list_id": "public.example.com",
    "list_name": "public",
    "mail_host": "example.com",
    "member_count": 25,
    "volume": 1,
    "description": "",
    "self_link": "http://localhost:9001/3.1/lists/public.example.com",
    "http_etag": "6jopcm1cq9kej328qeg3i766jw6v2gsu06mwo8fs",
}

MAILMAN_LIST_PRIVATE = {
    "advertised": False,
    "display_name": "private",
    "fqdn_listname": "private@example.com",
    "list_id": "private.example.com",
    "list_name": "private",
    "mail_host": "example.com",
    "member_count": 25,
    "volume": 1,
    "description": "",
    "self_link": "http://localhost:9001/3.1/lists/private.example.com",
    "http_etag": "6jopcm1cq9kej328qeg3i766jw6v2gsu06mwo8fs",
}

MAILMAN_LISTS = {
    'start': 0,
    'total_size': 2,
    'entries': [MAILMAN_LIST_PUBLIC, MAILMAN_LIST_PRIVATE],
}

MAILMAN_MEMBER = {
    'address': 'http://localhost:9001/3.1/addresses/holden.ford@example.com',
    'bounce_score': 0,
    'last_warning_sent': '0001-01-01T00:00:00',
    'total_warnings_sent': 0,
    'delivery_mode': 'regular',
    'email': 'holden.ford@example.com',
    'list_id': 'public.example.com',
    'subscription_mode': 'as_address',
    'role': 'member',
    'user': 'http://localhost:9001/3.1/users/ze5kwk6dgty03g6dtc3j27t6x0dlntlm',
    'moderation_action': 'defer',
    'display_name': 'Holden Ford',
    'self_link': 'http://localhost:9001/3.1/members/ze5kwk6dgty03g6dtc3j27t6x0dlntlm',
    'member_id': 'ze5kwk6dgty03g6dtc3j27t6x0dlntlm',
    'http_etag': '6jopcm1cq9kej328qeg3i766jw6v2gsu06mwo8fs',
}

MAILMAN_MEMBERS = {
    'start': 0,
    'total_size': 1,
    'entries': [MAILMAN_MEMBER],
}

# --------------------------------------------------
# Helper Classes
# --------------------------------------------------


class MailmanList:
    def __init__(self, list_name, member_count, mail_host='example.com'):
        self.list_name = list_name
        self.member_count = member_count
        self.mail_host = mail_host


class ListResponse:
    def __init__(self, lists):
        self.lists = lists


# --------------------------------------------------
# Tests
# --------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_export_lists():
    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    date_string = today_utc.strftime('%Y%m%d')
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.{}.xml'.format(date_string))
    if os.path.exists(path):
        os.remove(path)
    assert not os.path.exists(path)
    _export_lists()
    assert os.path.exists(path)


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


@patch('mailmanclient.restbase.connection.Connection.call')
@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_get_membership_3(mock_post, mock_client):
    # setup
    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    date_string = today_utc.strftime('%Y%m%d')
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.{}.xml'.format(date_string))
    if os.path.exists(path):
        os.remove(path)
    private = EmailListFactory.create(name='private', private=True)

    # prep mock
    response_lists = requests.Response()
    response_lists.status_code = 200
    response_lists._content = json.dumps(MAILMAN_LISTS).encode('ascii')
    response_list = requests.Response()
    response_list.status_code = 200
    response_list._content = json.dumps(MAILMAN_LIST_PRIVATE).encode('ascii')
    response_members = requests.Response()
    response_members.status_code = 200
    response_members._content = json.dumps(MAILMAN_MEMBERS).encode('ascii')
    response_lookup = requests.Response()
    response_lookup.status_code = 200
    response_lookup._content = b'{"person.person": {"1": {"user": {"username": "bperson@example.com"}}}}'
    mock_client.side_effect = [
        (response_lists, response_lists.json()),
        (response_lists, response_lists.json()),
        (response_list, response_list.json()),
        (response_members, response_members.json())]
    mock_post.return_value = response_lookup
    assert private.members.count() == 0
    get_membership_3(quiet=True)
    print(EmailList.objects.all())
    print(User.objects.all())
    assert private.members.count() == 1
    assert private.members.first().username == 'bperson@example.com'
    assert os.path.exists(path)


@patch('mailmanclient.client.Client.get_lists')
def test_get_fqdn(mock_client):
    mock_client.return_value = [MailmanList(
        list_name='public',
        member_count=1,
        mail_host='example.com')]
    assert get_fqdn('public') == 'public@example.com'


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
def test_update_mbox_files(tmpdir, settings, latin1_messages):
    settings.ARCHIVE_MBOX_DIR = str(tmpdir)
    yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    msg = Message.objects.last()
    assert msg.email_list.active is True
    assert msg.email_list.private is False
    msg.date = yesterday
    msg.save()
    assert len(os.listdir(tmpdir)) == 0
    update_mbox_files()
    print(str(tmpdir))
    path = os.path.join(tmpdir, 'public', msg.email_list.name)
    filename = '{}-{:02}.mail'.format(yesterday.year, yesterday.month)
    assert os.listdir(path) == [filename]
    mbox = mailbox.mbox(os.path.join(path, filename))
    assert len(mbox) == 1
    mbox_msg = mbox[0]
    assert mbox_msg['Message-Id'].strip('<>') == msg.msgid


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


@patch('mailmanclient.restbase.connection.Connection.call')
@pytest.mark.django_db(transaction=True)
def test_get_mailman_lists(mock_client):
    public = EmailListFactory.create(name='public')
    private = EmailListFactory.create(name='private', private=True)
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(MAILMAN_LISTS).encode('ascii')
    mock_client.return_value = response, response.json()
    mlists = get_mailman_lists(private=True)
    assert len(mlists) == 1
    assert list(mlists) == [private]


@patch('mailmanclient.restbase.connection.Connection.call')
@pytest.mark.django_db(transaction=True)
def test_get_subscribers(mock_client):
    public = EmailListFactory.create(name='public')
    response_fqdn = requests.Response()
    response_fqdn.status_code = 200
    response_fqdn._content = json.dumps(MAILMAN_LISTS).encode('ascii')
    response_a = requests.Response()
    response_a.status_code = 200
    response_a._content = json.dumps(MAILMAN_LIST_PUBLIC).encode('ascii')
    response_b = requests.Response()
    response_b.status_code = 200
    response_b._content = json.dumps(MAILMAN_MEMBERS).encode('ascii')
    mock_client.side_effect = [
        (response_fqdn, response_fqdn.json()),
        (response_a, response_a.json()),
        (response_b, response_b.json())]
    subs = get_subscribers('public')
    assert subs == ['holden.ford@example.com']


def test_purge_incoming(tmpdir, settings):
    path = str(tmpdir)
    settings.INCOMING_DIR = path
    # create new file
    new_file_path = os.path.join(path, 'new.txt')
    with open(new_file_path, 'w') as f:
        f.write("This is a test file.")

    old_file_path = os.path.join(path, 'old.txt') 
    with open(old_file_path, 'w') as f:
        f.write("This is a test file.")
    desired_mtime = time.time() - (86400 * 91)  # 91 days ago
    os.utime(old_file_path, (desired_mtime, desired_mtime))

    assert len(os.listdir(path)) == 2
    purge_incoming()
    assert len(os.listdir(path)) == 1
    assert os.path.exists(new_file_path)
    assert not os.path.exists(old_file_path)


def list_only_files(directory):
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]


@pytest.mark.django_db(transaction=True)
def test_move_list(rf, search_api_messages):
    source = 'acme'
    target = 'acme-archived'
    msg = Message.objects.filter(email_list__name=source).last()
    path = msg.get_file_path()
    old_url = msg.get_absolute_url()
    list_dir = os.path.dirname(path)
    new_list_dir = os.path.join(os.path.dirname(list_dir), target)
    # assert pre-conditions
    assert os.path.exists(path)
    assert len(list_only_files(list_dir)) == 4
    assert not os.path.exists(os.path.join(list_dir, target))
    assert Message.objects.filter(email_list__name=source).count() == 4
    assert Message.objects.filter(email_list__name=target).count() == 0
    # pre index state
    data = QueryDict('email_list=acme')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003', 'api004']
    # move messages
    move_list(source, target)
    # check files moved
    assert not os.path.exists(path)
    assert len(list_only_files(list_dir)) == 0
    assert os.path.exists(new_list_dir)
    assert len(list_only_files(new_list_dir)) == 4
    # check new hash
    new_hash = make_hash(msgid=msg.msgid, listname=target)
    msg.refresh_from_db()
    assert msg.hashcode == new_hash
    new_path = msg.get_file_path()
    assert new_hash in new_path
    assert os.path.exists(new_path)
    # check redirect table
    new_url = msg.get_absolute_url()
    assert new_url != old_url
    assert Redirect.objects.filter(old=old_url, new=new_url).exists()
    # check index updated
    data = QueryDict('email_list=acme')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 0
    data = QueryDict('email_list=acme-archived')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003', 'api004']
    # check db updated
    assert Message.objects.filter(email_list__name=source).count() == 0
    assert Message.objects.filter(email_list__name=target).count() == 4
