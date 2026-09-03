import datetime
import email
import io
import json
import mailbox
import pytest
import requests
from factories import EmailListFactory, MessageFactory, UserFactory, store_message_blob
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
    check_inactive, EmailList, purge_incoming,
    create_mbox_file, _get_lists_as_xml, get_subscribers, Subscriber,
    get_mailman_lists, get_membership, get_subscriber_counts, get_fqdn,
    update_mbox_files, _export_lists, move_list, remove_selected, mark_not_spam,
    is_duplicate_message, is_mailman_footer, import_message_blob,
    strip_mailman_footer, get_footer_tokens,
    create_cf_worker_templates, rebuild_json_blobs, _get_removed_message,
    audit_list_objects, reconcile_stored_objects)
from mlarchive.archive.models import User, Message, Redirect, MailmanMember, UserEmail
from mlarchive.archive.mail import make_hash, archive_message, MessageWrapper
from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.backends.elasticsearch import search_from_form
from mlarchive.archive.models import StoredObject
from mlarchive.archive.storage_utils import (store_file, get_unique_blob_name,
    exists_in_storage, store_str, list_names, remove_from_storage)
from mlarchive.blobdb.models import Blob
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


def _mock_membership_calls(mock_client, members=MAILMAN_MEMBERS):
    """Queue the mailman API responses get_membership() makes for one private list."""
    response_lists = requests.Response()
    response_lists.status_code = 200
    response_lists._content = json.dumps(MAILMAN_LISTS).encode('ascii')
    response_list = requests.Response()
    response_list.status_code = 200
    response_list._content = json.dumps(MAILMAN_LIST_PRIVATE).encode('ascii')
    response_members = requests.Response()
    response_members.status_code = 200
    response_members._content = json.dumps(members).encode('ascii')
    mock_client.side_effect = [
        (response_lists, response_lists.json()),        # get_mailman_lists
        (response_lists, response_lists.json()),        # get_fqdn_map
        (response_list, response_list.json()),          # client.get_list
        (response_members, response_members.json())]    # mailman_list.members


def _remove_export_file():
    """Remove today's list membership export file and return its path."""
    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    date_string = today_utc.strftime('%Y%m%d')
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.{}.xml'.format(date_string))
    if os.path.exists(path):
        os.remove(path)
    return path


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


@patch('mailmanclient.restbase.connection.Connection.call')
# @patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_get_membership(mock_client):
    # setup
    path = _remove_export_file()
    private = EmailListFactory.create(name='private', private=True)
    user = UserFactory.create()
    _ = UserEmail.objects.create(user=user, address='holden.ford@example.com')
    # prep mock
    _mock_membership_calls(mock_client)
    assert private.members.count() == 0
    assert MailmanMember.objects.count() == 0
    get_membership(quiet=True)
    assert MailmanMember.objects.filter(email_list=private).count() == 1
    print(EmailList.objects.all())
    print(User.objects.all())
    assert private.members.count() == 1
    assert private.members.first().username == 'admin'
    assert os.path.exists(path)


@patch('mailmanclient.restbase.connection.Connection.call')
@pytest.mark.django_db(transaction=True)
def test_get_membership_multiple_user_emails(mock_client):
    """A subscriber address known to more than one User grants access to both.

    This happens when someone changes their Datatracker primary email: OIDC
    creates a new User and both Users end up with a UserEmail record for the
    same address.
    """
    # setup
    path = _remove_export_file()
    private = EmailListFactory.create(name='private', private=True)
    old_user = UserFactory.create(username='holden.ford@example.com', email='holden.ford@example.com')
    new_user = UserFactory.create(username='hford@example.com', email='hford@example.com')
    UserEmail.objects.create(user=old_user, address='holden.ford@example.com')
    UserEmail.objects.create(user=new_user, address='holden.ford@example.com')
    # prep mock
    _mock_membership_calls(mock_client)
    assert private.members.count() == 0
    get_membership(quiet=True)
    assert MailmanMember.objects.filter(email_list=private).count() == 1
    assert private.members.count() == 2
    assert set(private.members.values_list('username', flat=True)) == set(
        ['holden.ford@example.com', 'hford@example.com'])
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
    # confirm private list ignored
    os.remove(path)
    elist.private = True
    elist.save()
    assert not os.path.exists(path)
    create_mbox_file(month=month, year=year, elist=elist)
    assert not os.path.exists(path)


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


@pytest.mark.django_db(transaction=True)
def test_purge_incoming(settings):
    bucket = 'ml-messages-incoming'
    old_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100)
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    with open(path, 'rb') as f:
        message_bytes = f.read()

    def store_old(prefix, content):
        """Store content in the incoming bucket and age its index row past the cutoff."""
        name = get_unique_blob_name(prefix=prefix, bucket=bucket)
        store_file(bucket, name, io.BytesIO(content), content_type='message/rfc822')
        StoredObject.objects.filter(store=bucket, name=name).update(modified=old_time)
        return name

    # Case 1: old object whose message was successfully archived → should be purged
    archive_message(data=message_bytes, listname='apple', private=False)
    archived_name = store_old('apple.public.', message_bytes)

    # Case 2: old object whose content exists in no other bucket → should NOT be purged.
    # Perturb the bytes so its digest differs from every stored object (content-based match).
    unverified_bytes = message_bytes + b'\nmake-content-unique\n'
    unverified_name = store_old('cherry.public.', unverified_bytes)

    # Case 3: recent object (within cutoff) → should NOT be purged
    recent_name = get_unique_blob_name(prefix='apple.public.', bucket=bucket)
    store_file(bucket, recent_name, io.BytesIO(message_bytes), content_type='message/rfc822')

    # Case 4: old object whose message exists in the removed bucket → should be purged
    path2 = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.2')
    with open(path2, 'rb') as f:
        removed_message_bytes = f.read()
    removed_mw = MessageWrapper.from_bytes(bytes=removed_message_bytes, listname='banana', private=False)
    removed_name_incoming = store_old('banana.public.', removed_message_bytes)
    removed_bucket_name = f'banana/{removed_mw.get_hash()}'.rstrip('=')
    store_file('ml-messages-removed', removed_bucket_name, io.BytesIO(removed_message_bytes), content_type='message/rfc822')

    # Case 5: old no-archive object with no stored copy → should be purged (dropped, not archived)
    noarchive_bytes = b'X-No-Archive: yes\n' + message_bytes
    noarchive_name = store_old('date.public.', noarchive_bytes)

    # Case 6: old object holding a redelivery of the message archived in case 1 → should be
    # purged. The extra header makes the bytes, and so the digest, differ from the
    # archived copy, so no object matches it. It is dropped as a redelivery without a copy
    # being stored anywhere, so purge_incoming() identifies it with the same check.
    redelivery_bytes = b'Received: from example.com by example.net\n' + message_bytes
    archive_message(data=redelivery_bytes, listname='apple', private=False)
    redelivery_name = store_old('apple.public.', redelivery_bytes)

    # Case 7: old object whose match is a tombstoned row → the match does not count,
    # and with no copy anywhere it is left in place
    tombstoned_bytes = message_bytes + b'\ntombstoned-copy\n'
    tombstoned_name = store_old('elder.public.', tombstoned_bytes)
    store_file('ml-messages-removed', 'elder/gone', io.BytesIO(tombstoned_bytes), content_type='message/rfc822')
    remove_from_storage('ml-messages-removed', 'elder/gone')

    stats = purge_incoming()

    assert stats == {'purged': 4, 'skipped': 2, 'errors': 0}
    assert not exists_in_storage(bucket, archived_name)
    assert exists_in_storage(bucket, unverified_name)
    assert exists_in_storage(bucket, recent_name)
    assert not exists_in_storage(bucket, removed_name_incoming)
    assert not exists_in_storage(bucket, noarchive_name)
    assert not exists_in_storage(bucket, redelivery_name)
    assert exists_in_storage(bucket, tombstoned_name)
    # the deletes went through the storage, so the index followed
    assert not StoredObject.objects.filter(store=bucket, name=archived_name).exclude_deleted().exists()
    assert StoredObject.objects.filter(store=bucket, name=unverified_name).exclude_deleted().exists()
    # dropped without a copy, so nothing was written to the dupes bucket
    assert list(list_names('ml-messages-dupes')) == []


@pytest.mark.django_db(transaction=True)
def test_purge_incoming_survives_bad_object(settings, caplog):
    """An index row whose bytes are gone is logged and skipped, not fatal to the run."""
    bucket = 'ml-messages-incoming'
    old_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100)
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    with open(path, 'rb') as f:
        message_bytes = f.read()

    orphan = get_unique_blob_name(prefix='apple.public.', bucket=bucket)
    store_file(bucket, orphan, io.BytesIO(b'bytes that will vanish'), content_type='message/rfc822')
    Blob.objects.get(bucket=bucket, name=orphan).delete()

    archive_message(data=message_bytes, listname='apple', private=False)
    archived = get_unique_blob_name(prefix='apple.public.', bucket=bucket)
    store_file(bucket, archived, io.BytesIO(message_bytes), content_type='message/rfc822')
    StoredObject.objects.filter(store=bucket).update(modified=old_time)

    stats = purge_incoming()

    assert stats == {'purged': 1, 'skipped': 0, 'errors': 1}
    assert not exists_in_storage(bucket, archived)
    assert f'purge_incoming: error processing {bucket}:{orphan}' in caplog.text


def list_only_files(directory):
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]


@pytest.mark.django_db(transaction=True)
def test_move_list(rf, search_api_messages):
    source = 'acme'
    target = 'acme-archived'
    msg = Message.objects.filter(email_list__name=source).last()
    path = msg.get_file_path()
    old_url = msg.get_absolute_url()
    old_blob_name = msg.get_blob_name()
    old_bucket = msg.get_blob_bucket()
    content = msg.get_raw_message()
    list_dir = os.path.dirname(path)
    new_list_dir = os.path.join(os.path.dirname(list_dir), target)
    # assert pre-conditions
    assert os.path.exists(path)
    assert len(list_only_files(list_dir)) == 4
    assert content
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
    # check blob moved
    assert not exists_in_storage(old_bucket, old_blob_name)
    assert msg.get_blob_name() != old_blob_name
    assert Message.objects.get(pk=msg.pk).get_raw_message() == content
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


@pytest.mark.django_db(transaction=True)
def test_remove_selected(client, search_api_messages_ford, users):
    user = User.objects.get(username='staff@example.com')
    msg = Message.objects.first()
    # remove mbox file if it already exists
    mbox_filename = '{:04d}-{:02d}.mail'.format(msg.date.year, msg.date.month)
    mbox_path = os.path.join(settings.ARCHIVE_MBOX_DIR, 'public', msg.email_list.name, mbox_filename)
    if os.path.exists(mbox_path):
        os.remove(mbox_path)
    # mark message for removal
    msg.spam_score = settings.SPAM_SCORE_TO_REMOVE
    msg.save()
    path = msg.get_file_path()
    assert os.path.isfile(path)
    totalb4 = Message.objects.count()
    remove_selected(user_id=user.id)
    assert Message.objects.count() == totalb4 - 1
    assert not Message.objects.filter(id=msg.id).exists()
    # check file moved
    assert not os.path.isfile(path)
    target = os.path.join(msg.get_removed_dir(), msg.hashcode)
    assert os.path.isfile(target)
    # check mbox update
    assert os.path.isfile(mbox_path)


@pytest.mark.django_db(transaction=True)
def test_mark_not_spam(client, messages):
    assert Message.objects.filter(spam_score=settings.SPAM_SCORE_NOT_SPAM).count() == 0
    queryset = Message.objects.filter(email_list__name='pubone')
    mark_not_spam(queryset)
    assert Message.objects.filter(spam_score=settings.SPAM_SCORE_NOT_SPAM).count() == queryset.count()
    assert queryset.first().spam_score == settings.SPAM_SCORE_NOT_SPAM


@pytest.mark.django_db(transaction=True)
def test_import_message_blob(client):
    # test setup
    bucket = 'ml-messages-incoming'
    blob_name = get_unique_blob_name(prefix='apple.public.', bucket=bucket)
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    with open(path, 'rb') as f:
        message = f.read()
    store_file(bucket, blob_name, io.BytesIO(message), content_type='message/rfc822')

    assert Blob.objects.filter(
        bucket='ml-messages-incoming',
        name__startswith='apple.public',
    ).count() == 1

    assert not EmailList.objects.filter(name='apple', private=False).exists()
    assert not Message.objects.exists()

    # call import
    import_message_blob(bucket=bucket, name=blob_name)

    # assert list exists
    assert EmailList.objects.filter(name='apple', private=False).exists()

    # assert message exists, message-id
    msg = Message.objects.get(email_list__name='apple', msgid='0000000001@amsl.com')
    assert msg.subject == 'This is a test'

    # assert message blob exists in archive storage
    storage_blob_name = f'apple/{msg.hashcode.strip('=')}'
    assert exists_in_storage('ml-messages', storage_blob_name)
    assert exists_in_storage('ml-messages-json', storage_blob_name)


# --------------------------------------------------
# Tests for is_duplicate_message
# --------------------------------------------------

def test_is_duplicate_message_identical():
    """Test that two identical messages are detected as duplicates."""
    mbox_path = os.path.join(os.path.dirname(__file__), '../data/duplicate_tests.mbox')
    mbox = mailbox.mbox(mbox_path)
    msg1 = email.message_from_bytes(bytes(mbox[0]))  # Control message
    msg2 = email.message_from_bytes(bytes(mbox[1]))  # Identical copy
    assert is_duplicate_message(msg1, msg2) is True
    mbox.close()


def test_is_duplicate_message_different_received_headers():
    """Test that messages with different Received headers but same content are duplicates."""
    mbox_path = os.path.join(os.path.dirname(__file__), '../data/duplicate_tests.mbox')
    mbox = mailbox.mbox(mbox_path)
    msg1 = email.message_from_bytes(bytes(mbox[0]))  # Control message
    msg3 = email.message_from_bytes(bytes(mbox[2]))  # Different Received headers
    assert is_duplicate_message(msg1, msg3) is True
    mbox.close()


def test_is_duplicate_message_doubled_mailman_footers():
    """Test that messages with doubled Mailman footers are considered duplicates."""
    mbox_path = os.path.join(os.path.dirname(__file__), '../data/duplicate_tests.mbox')
    mbox = mailbox.mbox(mbox_path)
    msg4 = email.message_from_bytes(bytes(mbox[3]))  # Multipart with one footer
    msg5 = email.message_from_bytes(bytes(mbox[4]))  # Multipart with doubled footers
    assert is_duplicate_message(msg4, msg5) is True
    mbox.close()


def test_is_duplicate_message_different_content():
    """Test that messages with same Message-ID but different content are NOT duplicates."""
    mbox_path = os.path.join(os.path.dirname(__file__), '../data/duplicate_tests.mbox')
    mbox = mailbox.mbox(mbox_path)
    msg1 = email.message_from_bytes(bytes(mbox[0]))  # Control message
    msg6 = email.message_from_bytes(bytes(mbox[5]))  # Different content, same Message-ID
    assert is_duplicate_message(msg1, msg6) is False
    mbox.close()


def test_is_duplicate_message_different_message_id():
    """Test that messages with different Message-IDs are NOT duplicates."""
    mbox_path = os.path.join(os.path.dirname(__file__), '../data/duplicate_tests.mbox')
    mbox = mailbox.mbox(mbox_path)
    msg1 = email.message_from_bytes(bytes(mbox[0]))  # Control message
    msg7 = email.message_from_bytes(bytes(mbox[6]))  # Same content, different Message-ID
    assert is_duplicate_message(msg1, msg7) is False
    mbox.close()


def test_is_mailman_footer_detection():
    """Test that Mailman footers are correctly detected."""
    mbox_path = os.path.join(os.path.dirname(__file__), '../data/duplicate_tests.mbox')
    mbox = mailbox.mbox(mbox_path)
    msg8 = email.message_from_bytes(bytes(mbox[7]))  # Valid Mailman footer
    parts = [part for part in msg8.walk()]
    assert is_mailman_footer(parts[-1]) is True
    msg9 = email.message_from_bytes(bytes(mbox[8]))  # Not a Mailman footer - doesn't start with ___
    parts = [part for part in msg9.walk()]
    assert is_mailman_footer(parts[-1]) is False
    msg10 = email.message_from_bytes(bytes(mbox[9]))  # Not a Mailman footer - missing "listinfo"
    parts = [part for part in msg10.walk()]
    assert is_mailman_footer(parts[-1]) is False
    mbox.close()


MM2_FOOTER = (b'_______________________________________________\n'
              b'testlist mailing list\n'
              b'testlist@ietf.org\n'
              b'https://www.ietf.org/mailman/listinfo/testlist\n')

MM3_FOOTER = (b'_______________________________________________\n'
              b'testlist mailing list -- testlist@ietf.org\n'
              b'To unsubscribe send an email to testlist-leave@ietf.org\n')


def build_message(body, extra_headers=b'', msgid=b'<control@example.com>'):
    """Build an email.message.Message with the given body"""
    return email.message_from_bytes(
        b'From: Joe <joe@example.com>\n'
        b'To: testlist@ietf.org\n'
        b'Subject: This is a test\n'
        b'Message-ID: ' + msgid + b'\n'
        + extra_headers
        + b'Content-Type: text/plain; charset="us-ascii"\n'
        b'\n' + body)


def test_strip_mailman_footer_mailman2():
    assert strip_mailman_footer(b'Hello.\n\n' + MM2_FOOTER) == b'Hello.\n\n'


def test_strip_mailman_footer_mailman3():
    """Mailman 3 uses the same separator but different wording, no listinfo URL"""
    assert strip_mailman_footer(b'Hello.\n\n' + MM3_FOOTER) == b'Hello.\n\n'


def test_strip_mailman_footer_leaves_underscore_rule_in_body():
    """A rule of underscores is common in ordinary mail. Truncating there would make two
    different messages compare equal, dropping a message that should have been archived
    """
    body = (b'Hello.\n'
            b'____________________\n'
            b'Name:  ____________\n'
            b'Date:  ____________\n'
            b'Return the form above to the secretariat.\n'
            b'Thanks.\n')
    assert strip_mailman_footer(body) == body


def test_is_duplicate_message_differs_after_underscore_rule():
    """The consequence of the above: content below a rule of underscores is compared"""
    msg1 = build_message(b'Hello.\n____________________\nOption A please.\n')
    msg2 = build_message(b'Hello.\n____________________\nOption B please.\n')
    assert is_duplicate_message(msg1, msg2) is False


def test_strip_mailman_footer_last_separator_only():
    """Only the block below the last separator is a candidate footer"""
    body = b'Hello.\n____________________\nstill body\n\n' + MM2_FOOTER
    assert strip_mailman_footer(body) == b'Hello.\n____________________\nstill body\n\n'


def test_strip_mailman_footer_size_bound():
    """A large block below a separator is content, whatever wording it contains"""
    body = b'Hello.\n' + b'_' * 47 + b'\n' + b'x' * 600 + b'\n/listinfo/testlist\n'
    assert strip_mailman_footer(body) == body


def test_strip_mailman_footer_identified_by_list_headers():
    """A footer whose wording is not recognised is still identified by the list address
    taken from the message's List-* headers"""
    footer = (b'_______________________________________________\n'
              b'testlist discussion group\n'
              b'testlist@ietf.org\n')
    body = b'Hello.\n\n' + footer
    msg = build_message(body, extra_headers=b'List-Post: <mailto:testlist@ietf.org>\n')
    assert strip_mailman_footer(body, msg) == b'Hello.\n\n'
    # with no headers to go on there is nothing identifying it as a footer
    assert strip_mailman_footer(body) == body


def test_get_footer_tokens():
    msg = build_message(
        b'Hello.\n',
        extra_headers=b'List-Post: <mailto:testlist@ietf.org>\n'
                      b'List-Unsubscribe: <https://example.com/lists/testlist>,\n'
                      b' <mailto:testlist-leave@ietf.org?subject=unsubscribe>\n')
    tokens = get_footer_tokens(msg)
    assert b'testlist@ietf.org' in tokens
    assert b'testlist-leave@ietf.org' in tokens
    assert b'https://example.com/lists/testlist' in tokens
    assert get_footer_tokens(None) == []


def test_is_mailman_footer_mailman3_part():
    """A Mailman 3 footer carried as its own part has no listinfo URL"""
    raw = (b'From: Joe <joe@example.com>\n'
           b'Message-ID: <control@example.com>\n'
           b'Content-Type: multipart/mixed; boundary="BOUND"\n'
           b'\n'
           b'--BOUND\n'
           b'Content-Type: text/plain\n'
           b'\n'
           b'Hello.\n'
           b'--BOUND\n'
           b'Content-Type: text/plain\n'
           b'\n' + MM3_FOOTER +
           b'--BOUND--\n')
    msg = email.message_from_bytes(raw)
    parts = [part for part in msg.walk() if not part.is_multipart()]
    assert is_mailman_footer(parts[-1]) is True
    assert is_mailman_footer(parts[0]) is False


def test_is_duplicate_message_leading_whitespace_is_content():
    """Only trailing whitespace is trimmed, indentation is part of the body"""
    msg1 = build_message(b'    indented\nbody\n')
    msg2 = build_message(b'indented\nbody\n')
    assert is_duplicate_message(msg1, msg2) is False


def test_create_cf_worker_templates():
    """Test the creation of the Cloudflare worker message edge template"""
    create_cf_worker_templates()
    path = os.path.join(settings.CF_WORKER_TEMPLATE_DIR, 'message-detail.html')
    assert os.path.exists(path)


@pytest.mark.django_db(transaction=True)
def test_rebuild_json_blobs():
    from mock import patch

    public = EmailListFactory(name='rebuild-test', private=False)
    msg1 = MessageFactory.create(email_list=public)
    msg2 = MessageFactory.create(email_list=public)
    messages = [msg1, msg2]
    names = [m.get_blob_name() for m in messages]

    # JSON blobs are written by MessageWrapper.save(), not on Message save,
    # so messages created directly have none
    assert Blob.objects.filter(bucket='ml-messages-json', name__in=names).count() == 0

    # create path: missing blobs get created
    with patch('mlarchive.archive.utils.replicate_batch', return_value=[]):
        failures = rebuild_json_blobs(messages)

    assert failures == []
    assert Blob.objects.filter(bucket='ml-messages-json', name__in=names).count() == 2

    # update path: existing blobs get re-written
    with patch('mlarchive.archive.utils.replicate_batch', return_value=[]):
        failures = rebuild_json_blobs(messages)

    assert failures == []
    assert Blob.objects.filter(bucket='ml-messages-json', name__in=names).count() == 2


# Tests for _get_removed_message
# --------------------------------------------------

def test_get_removed_message_returns_email_object(tmp_path):
    raw = (
        b"From: a@example.com\r\n"
        b"Message-ID: <abc@example.com>\r\n"
        b"Subject: test\r\n\r\n"
        b"Body\r\n"
    )
    removed_file = tmp_path / "removed_msg"
    removed_file.write_bytes(raw)

    removed_message_ids = {"abc@example.com": str(removed_file)}

    result = _get_removed_message("abc@example.com", removed_message_ids)

    assert result is not None
    assert result["Message-ID"] == "<abc@example.com>"


@pytest.mark.django_db(transaction=True)
def test_audit_list_objects():
    elist = EmailListFactory.create(name='acme')
    stored = MessageFactory.create(email_list=elist)
    store_message_blob(stored, b'stored message')
    lost = MessageFactory.create(email_list=elist)
    other = EmailListFactory.create(name='acme-wg')
    MessageFactory.create(email_list=other, hashcode=lost.hashcode)
    store_str('ml-messages', 'acme/orphanhash', content='no message owns me')
    store_str('ml-messages', 'acme-wg/otherorphan', content='different list')
    store_str('ml-messages-removed', 'acme/removedhash', content='different bucket')

    only_messages, only_objects = audit_list_objects(elist)

    assert only_messages == {lost.hashcode.rstrip('=')}
    assert only_objects == {'orphanhash'}


@pytest.mark.django_db(transaction=True)
def test_audit_list_objects_private_list():
    elist = EmailListFactory.create(name='secret', private=True)
    message = MessageFactory.create(email_list=elist)
    store_message_blob(message, b'private message')
    store_str('ml-messages', 'secret/publicorphan', content='wrong bucket')

    assert audit_list_objects(elist) == (set(), set())


@pytest.mark.django_db(transaction=True)
def test_reconcile_stored_objects():
    public = EmailListFactory.create(name='acme')
    private = EmailListFactory.create(name='secret', private=True)
    for elist in (public, private):
        message = MessageFactory.create(email_list=elist)
        store_message_blob(message, b'stored message')
    lost = MessageFactory.create(email_list=public)
    store_str('ml-messages', 'acme/orphan', content='no message')
    # bytes written behind the storage's back, in a bucket no list uses
    Blob.objects.update_or_create(
        bucket='ml-messages-spam', name='acme/spam', defaults={'content': b'spam'})

    stats = reconcile_stored_objects()

    assert stats['rows'] == 3
    assert stats['objects'] == 4
    assert stats['untracked'] == 1
    assert stats['repaired'] == 0
    assert stats['lists'] == 2
    assert stats['list_mismatches'] == 1
    assert stats['only_messages'] == 1
    assert stats['only_objects'] == 1
    assert not StoredObject.objects.filter(store='ml-messages-spam').exists()

    stats = reconcile_stored_objects(repair=True)
    assert stats['untracked'] == 1
    assert stats['repaired'] == 1
    assert StoredObject.objects.get(store='ml-messages-spam', name='acme/spam').deleted is None

    stats = reconcile_stored_objects()
    assert stats['rows'] == 4
    assert stats['untracked'] == 0
    assert stats['only_messages'] == 1
    assert lost.hashcode.rstrip('=') not in [
        name.split('/')[1] for name in StoredObject.objects.values_list('name', flat=True)]


@pytest.mark.django_db(transaction=True)
def test_reconcile_stored_objects_single_bucket():
    public = EmailListFactory.create(name='acme')
    private = EmailListFactory.create(name='secret', private=True)
    MessageFactory.create(email_list=public)
    MessageFactory.create(email_list=private)
    store_str('ml-messages-private', 'secret/orphan', content='x')

    stats = reconcile_stored_objects(bucket='ml-messages-private')
    assert stats['rows'] == 1
    assert stats['lists'] == 1
    assert stats['only_messages'] == 1
    assert stats['only_objects'] == 1

    stats = reconcile_stored_objects(bucket='ml-messages-json')
    assert stats['rows'] == 0
    assert stats['lists'] == 0

    with pytest.raises(ValueError):
        reconcile_stored_objects(bucket='ml-nonsense')
