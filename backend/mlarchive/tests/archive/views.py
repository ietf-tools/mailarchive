import csv
import datetime
import io
import os
import pytest
import tarfile
from datetime import timezone
from email.utils import parseaddr
from dateutil.relativedelta import relativedelta
from urllib import parse
from pyquery import PyQuery

from django.contrib.auth import SESSION_KEY
from django.test import RequestFactory
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.encoding import smart_str
from factories import EmailListFactory, MessageFactory, UserFactory, SubscriberFactory
from mlarchive.archive.models import Message, Attachment, Redirect
from mlarchive.archive.views import (TimePeriod, add_nav_urls, is_small_year,
    get_this_next_periods, get_date_endpoints, get_thread_endpoints, DateStaticIndexView)
from mlarchive.utils.test_utils import login_testing_unauthorized
from mlarchive.utils.test_utils import load_message


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def assert_href(content, selector, value):
    q = PyQuery(content)
    assert q(selector).attr('href') == value


@pytest.mark.django_db(transaction=True)
def test_add_nav_urls(static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    time_period = TimePeriod(year=2016, month=None)
    context = dict(group_by_thread=False, time_period=time_period, email_list=static_list)
    add_nav_urls(context)
    assert '2015' in context['previous_page'] 
    assert '2017-12' in context['next_page']
    context['time_period'] = TimePeriod(year=2015, month=6)
    add_nav_urls(context)
    assert context['previous_page'] == ''
    context['time_period'] = TimePeriod(year=2017, month=12)
    add_nav_urls(context)
    assert context['next_page'] == ''


@pytest.mark.django_db(transaction=True)
def test_is_small_year(static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    assert is_small_year(static_list, '2015') is True
    assert is_small_year(static_list, '2017') is False


@pytest.mark.django_db(transaction=True)
def test_get_thread_endpoints(static_list):
    time_period = TimePeriod(year=2016, month=6)
    previous_message, next_message = get_thread_endpoints(static_list, time_period)
    assert previous_message == static_list.message_set.filter(thread__date__year=2015).order_by('date').last()
    assert next_message == static_list.message_set.filter(thread__date__year=2017).order_by('date').first()


@pytest.mark.django_db(transaction=True)
def test_get_date_endpoints(static_list):
    time_period = TimePeriod(year=2016, month=6)
    previous_message, next_message = get_date_endpoints(static_list, time_period)
    assert previous_message == static_list.message_set.filter(date__year=2015).order_by('date').last()
    assert next_message == static_list.message_set.filter(date__year=2017).order_by('date').first()


@pytest.mark.django_db(transaction=True)
def test_get_this_next_periods(static_list):
    time_period = TimePeriod(year=2017, month=4)
    assert get_this_next_periods(time_period) == (
        datetime.datetime(2017, 4, 1, tzinfo=timezone.utc),
        datetime.datetime(2017, 5, 1, tzinfo=timezone.utc))
    time_period = TimePeriod(year=2017, month=None)
    assert get_this_next_periods(time_period) == (
        datetime.datetime(2017, 1, 1, tzinfo=timezone.utc),
        datetime.datetime(2018, 1, 1, tzinfo=timezone.utc))
    # test leap year
    time_period = TimePeriod(year=2024, month=None)
    assert get_this_next_periods(time_period) == (
        datetime.datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime.datetime(2025, 1, 1, tzinfo=timezone.utc))


# --------------------------------------------------
# Tests
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_admin(client, admin_client):
    "Admin Test"
    url = reverse('archive_admin')
    response = client.get(url)
    assert response.status_code == 403
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_admin_search_msgid(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?msgid=' + msg.msgid
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert str(msg.pk) in [r.django_id for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_subject(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?subject=message'
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert str(msg.pk) in [r.django_id for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_date(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?start_date=' + msg.date.strftime("%Y-%m-%d")
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert str(msg.pk) in [r.django_id for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_list(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?email_list=' + msg.email_list.name
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert str(msg.pk) in [r.django_id for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_no_action(admin_client, messages):
    url = reverse('archive_admin')
    response = admin_client.post(url, {'select-across': 0, 'index': 0})
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_admin_search_from(client, messages):
    msg = Message.objects.first()
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    realname, email_address = parseaddr(msg.frm)
    # test search email address portion
    url = reverse('archive_admin') + '?frm=' + email_address
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert str(msg.pk) in [r.django_id for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_menu(client, admin_client):
    url = reverse('archive')
    response = client.get(url)
    assert 'id="navbar-admin"' not in smart_str(response.content)
    response = admin_client.get(url)
    assert 'id="navbar-admin"' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_admin_console(client, admin_client):
    url = reverse('archive_admin_console')
    response = client.get(url)
    assert response.status_code == 302
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_admin_guide(client, admin_client):
    url = reverse('archive_admin_guide')
    response = client.get(url)
    assert response.status_code == 403
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_advsearch(client, messages):
    url = reverse('archive_advsearch')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_browse(client):
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_browse_list(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'})
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_browse_list_private(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'private'})
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_browse_list_bogus_index(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'}) + '?index={}'.format('x' * 27)
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_browse_list_mixed_unicode(client, messages):
    '''This is a test which comes from bogus requests
    to the production system. The mixed 3byte and 4byte
    unicode in the URL caused Illegal mix of collation
    errors when using utf8mb3 database character set.
    Switch to utf8mb4 to resolve.
    '''
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'})
    REPLACEMENT_CHARACTER = '%EF%BF%BD'     # 3byte code
    ELECTRIC_LIGHT_BULB = '%F0%9F%92%A1'    # 4byte code
    path = f"/arch/browse/email_list%20=%20{REPLACEMENT_CHARACTER}%5C{ELECTRIC_LIGHT_BULB}"
    parts = parse.urlsplit(url)
    new_parts = parts._replace(path=path)
    garbage_url = parse.urlunsplit(new_parts)
    response = client.get(garbage_url, follow=True)
    print(garbage_url)
    print(parts)
    print(response.status_code)
    # print(response['location'])
    # assert False
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_browse_query(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'}) + '?q=invitation'
    response = client.get(url)
    assert response.status_code == 200
    for r in response.context['results']:
        print(r.date, r.subject)
    assert len(response.context['results']) == 3
    assert response.context['queryid']


@pytest.mark.django_db(transaction=True)
def test_browse_gbt(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'apple'}) + '?gbt=1'
    messages = messages.filter(email_list__name='apple').order_by('thread_order')
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 6
    # assert proper order
    assert [r.pk for r in response.context['results']] == [m.pk for m in messages]


@pytest.mark.django_db(transaction=True)
def test_browse_list_sort_subject(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'}) + '?so=subject'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 5
    # assert proper order
    assert [r.msgid for r in response.context['results']] == ['a01', 'a02', 'a04', 'a03', 'a05']


@pytest.mark.django_db(transaction=True)
def test_browse_index_gbt(client, messages):
    message = messages.get(msgid='a02')
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'}) + '?gbt=1&index={}'.format(message.hashcode.strip('='))
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 5


@pytest.mark.django_db(transaction=True)
def test_browse_static_mode(client):
    elist = EmailListFactory.create()
    url = reverse('archive_browse_list', kwargs={'list_name': elist.name})
    client.cookies['isStaticOn'] = 'true'
    response = client.get(url)
    assert response.status_code == 302
    assert response['location'] == reverse('archive_browse_static', kwargs={'list_name': elist.name})


@pytest.mark.django_db(transaction=True)
def test_browse_qdr(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubthree'}) + '?qdr=d'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 1

    url = reverse('archive_browse_list', kwargs={'list_name': 'pubthree'}) + '?qdr=w'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 7

    url = reverse('archive_browse_list', kwargs={'list_name': 'pubthree'}) + '?qdr=m'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 20


@pytest.mark.django_db(transaction=True)
def test_browse_qdr_invalid(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubthree'}) + '?qdr=3d'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 20


@pytest.mark.django_db(transaction=True)
def test_browse_static(client, messages):
    url = reverse('archive_browse_static')
    response = client.get(url)
    assert response.status_code == 200
    msg = messages.filter(email_list__private=False).first()
    assert msg.email_list.name in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_browse_static_date(client, static_list):
    url = reverse('archive_browse_static_date', kwargs={'list_name': static_list.name, 'date': '2017'})
    request = RequestFactory().get(url)
    request.COOKIES['isStaticOn'] = 'true'
    response = DateStaticIndexView.as_view()(request, list_name=static_list.name, date='2017')
    assert response.status_code == 200
    # ensure no login info in header, we don't want it cached
    q = PyQuery(response.content)
    assert len(q('#login')) == 0


@pytest.mark.django_db(transaction=True)
def test_browse_static_unauthorized(client):
    now = datetime.datetime.now(timezone.utc)
    elist = EmailListFactory.create(name='private', private=True)
    message = MessageFactory.create(email_list=elist, date=now)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': now.year})
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_browse_static_cache_headers_private(admin_client):
    '''Ensure private lists include Cache-Control: private header'''
    now = datetime.datetime.now(timezone.utc)
    elist = EmailListFactory.create(name='private', private=True)
    message = MessageFactory.create(email_list=elist, date=now)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': '{}-{:02d}'.format(now.year, now.month)})
    response = admin_client.get(url)
    assert response.status_code == 200
    assert 'no-cache' in response.get('Cache-Control')


@pytest.mark.django_db(transaction=True)
def test_browse_static_cache_headers_public(client):
    '''Ensure private lists include Cache-Control: private header'''
    now = datetime.datetime.now(timezone.utc)
    elist = EmailListFactory.create()
    message = MessageFactory.create(email_list=elist, date=now)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': now.year})
    response = client.get(url)
    assert response.status_code == 200
    cache_control = response.get('Cache-Control')
    assert cache_control is None or 'no-cache' not in cache_control


@pytest.mark.django_db(transaction=True)
def test_browse_static_small_year_year(client, static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    url = reverse('archive_browse_static_date', kwargs={'list_name': static_list.name, 'date': '2015'})
    response = client.get(url)
    assert response.status_code == 200
    print(response.content)
    q = PyQuery(response.content)
    assert len(q('ul.static-index li')) == 15

    # no messages
    # assert 'No messages' in content
    # assert_href(content, 'a.next', '2017-12')
    # assert_href(content, 'a.previous', '2015')
    # < STATIC_INDEX_YEAR_MINIMUM
    # q = PyQuery(content)
    # assert len(q('ul.static-index li')) == 15
    # assert_href(content, 'a.next', '2017-12')
    # assert len(q('a.previous')) == 0

@pytest.mark.django_db(transaction=True)
def test_browse_static_small_year_month(client, static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    url = reverse('archive_browse_static_date', kwargs={'list_name': static_list.name, 'date': '2015-06'})
    response = client.get(url)
    assert response.status_code == 200
    assert 'http-equiv="refresh"' in smart_str(response.content)
    assert 'public/2015' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_browse_static_small_year_current(client, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    now = datetime.datetime.now(timezone.utc)
    current_year = now.year
    elist = EmailListFactory.create()
    message = MessageFactory.create(email_list=elist, date=now)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': '{}-{:02d}'.format(now.year, now.month)})
    response = client.get(url)
    assert response.status_code == 200
    assert message.subject in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_browse_static_big_year_year(client, static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    url = reverse('archive_browse_static_date', kwargs={'list_name': static_list.name, 'date': '2017'})
    response = client.get(url)
    assert response.status_code == 200
    assert 'http-equiv="refresh"' in smart_str(response.content)
    assert 'public/2017-12' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_browse_static_redirect(client, static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    url = reverse('archive_browse_static', kwargs={'list_name': static_list.name})
    response = client.get(url)
    assert response.status_code == 302
    assert response['location'] == reverse('archive_browse_static_date', kwargs={'list_name': static_list.name, 'date': '2017-12'})


@pytest.mark.django_db(transaction=True)
def test_browse_static_redirect_empty(client):
    elist = EmailListFactory.create()
    year = datetime.datetime.now(timezone.utc).year
    url = reverse('archive_browse_static', kwargs={'list_name': elist.name})
    response = client.get(url)
    assert response.status_code == 302
    assert response['location'] == reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': year})


@pytest.mark.django_db(transaction=True)
def test_detail(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('archive_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    assert '<title>{}</title>'.format(msg.subject) in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_detail_bad_content_transfer_encoding(client):
    '''Test that message with content_transfer_encoding = "base64 ",
    with trailing whitespace is decoded properly
    '''
    listname = 'public'
    load_message('bad_transfer_encoding.mail', listname=listname)
    msg = Message.objects.first()
    url = reverse('archive_detail', kwargs={'list_name': listname, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    print(response.content)
    assert 'Hello. Testing' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_detail_bad_to_address(client):
    '''Test that message with bad To address doesn't break detail view.
    To address contains "::;"
    '''
    listname = 'public'
    load_message('bad_to_address.mail', listname=listname)
    msg = Message.objects.first()
    url = reverse('archive_detail', kwargs={'list_name': listname, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    # print(response.content)
    # from mlarchive.archive.generator import Generator
    # g = Generator(msg)
    # text = g.as_text()
    # print(text)
    # print(msg.get_body())
    import email
    from email import policy
    path = msg.get_file_path()
    with open(path, 'rb') as f:
        m = email.message_from_binary_file(f, policy=policy.compat32)
    assert isinstance(m, email.message.Message)
    print(vars(m))
    print(msg.get_file_path())
    assert 'Hello. Testing' in smart_str(response.content)


@pytest.mark.skip(reason='Not representative of data ?')
@pytest.mark.django_db(transaction=True)
def test_detail_bad_date(client):
    '''Test that message with bad date header doesn't break detail view.
    Date header is very old like: Date: 04-Jan-93 13:22:13
    '''
    listname = 'public'
    load_message('bad_date.mail', listname=listname)
    print(Message.objects.count())
    msg = Message.objects.first()
    url = reverse('archive_detail', kwargs={'list_name': listname, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    print(response.content)
    assert 'Hello. Testing' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_detail_content_link(client):
    '''Test that url in message content appears as a link'''
    listname = 'public'
    load_message('mail_with_url.1', listname=listname)
    msg = Message.objects.first()
    url = reverse('archive_detail', kwargs={'list_name': listname, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('a[href="http://www.example.com"]')) == 1


@pytest.mark.django_db(transaction=True)
def test_detail_admin_access(client):
    '''Test that admin user gets link to admin site,
    regular user does not'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    UserFactory.create(is_staff=True)
    url = reverse('archive_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    # not logged in
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#admin-link')) == 0
    # priviledged user
    client.login(username='admin', password='admin')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#admin-link')) == 1


@pytest.mark.django_db(transaction=True)
def test_detail_cache_headers_public(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('archive_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    cache_control = response.get('Cache-Control')
    assert cache_control is None or 'no-cache' not in cache_control


@pytest.mark.django_db(transaction=True)
def test_detail_cache_headers_private(admin_client):
    elist = EmailListFactory.create(name='private', private=True)
    msg = MessageFactory.create(email_list=elist)
    url = reverse('archive_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = admin_client.get(url)
    assert response.status_code == 200
    assert 'no-cache' in response.get('Cache-Control')


@pytest.mark.django_db(transaction=True)
def test_attachment(client, attachment_messages_no_index):
    message = Message.objects.get(msgid='attachment')
    attachment = message.attachment_set.first()
    url = reverse('archive_attachment', kwargs={'list_name': attachment.message.email_list.name,
                                                'id': attachment.message.hashcode,
                                                'sequence': attachment.sequence})
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/plain'
    assert response['Content-Disposition'] == 'attachment; filename=skip32.c'
    assert 'unsigned' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_attachment_windows1252(client, attachment_messages_no_index):
    print(Message.objects.values_list('msgid'))
    message = Message.objects.get(msgid='attachment_windows1252')
    attachment = message.attachment_set.first()
    url = reverse('archive_attachment', kwargs={'list_name': attachment.message.email_list.name,
                                                'id': attachment.message.hashcode,
                                                'sequence': attachment.sequence})
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/plain'


@pytest.mark.django_db(transaction=True)
def test_attachment_bad_sequence(client, attachment_messages_no_index):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('archive_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = client.get(url + 'xyz)/')
    assert response.status_code == 404

    # message = Message.objects.get(msgid='attachment')
    # attachment = message.attachment_set.first()
    # response = client.get(url)
    # assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_attachment_folded_name(client, attachment_messages_no_index):
    message = Message.objects.get(msgid='attachment.folded.name')
    attachment = message.attachment_set.first()
    url = reverse('archive_attachment', kwargs={'list_name': attachment.message.email_list.name,
                                                'id': attachment.message.hashcode,
                                                'sequence': attachment.sequence})
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/plain'
    assert response['Content-Disposition'] == 'attachment; filename=this_is_a really_long filename'
    assert 'unsigned' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_attachment_message_rfc822(client, attachment_messages_no_index):
    assert Attachment.objects.filter(content_type='message/rfc822').count() == 0


@pytest.mark.django_db(transaction=True)
def test_export(admin_client, export_messages):
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?email_list=acme'
    response = admin_client.get(url)
    print(url)
    print(response.headers)
    assert response.status_code == 200
    assert response['Content-Disposition'].startswith('attachment;')
    assert response['Content-Type'] == 'application/x-tar-gz'
    # ensure we are getting all messages in response
    file_like_object = io.BytesIO(response.content)
    tar = tarfile.open(fileobj=file_like_object)
    count = 0 
    # q&d way to count total messages
    for member in tar.getmembers():
        f = tar.extractfile(member)
        for line in f.readlines():
            if line.startswith(b'From '):
                count = count + 1
    assert count == 21


@pytest.mark.django_db(transaction=True)
def test_export_datatracker_api(client, thread_messages):
    '''Datatracker uses this interface from the complete-a-review view.
    Note: no login is required
    '''
    params = {'subject': 'anvil',
              'email_list': 'acme',
              'as': '1',
              'qdr': 'c',
              'start_date': '2010-01-01'}
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?' + urlencode(params)
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Disposition'].startswith('attachment;')
    assert response['Content-Type'] == 'application/x-tar-gz'


'''
# Temporarily removed
@pytest.mark.django_db(transaction=True)
def test_export_not_logged_in(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'})
    response = client.get(url)
    assert response.status_code == 200
    assert 'You must be logged in to export messages.' in response.content
    q = PyQuery(response.content)
    assert len(q('.export-link.disabled')) == 3
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?email_list=pubone'
    response = client.get(url)
    assert response.status_code == 302
'''


@pytest.mark.django_db(transaction=True)
def test_export_limit(client, admin_client, messages, settings, users):
    settings.EXPORT_LIMIT = 0
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'})
    assert client.login(username='unprivileged@example.com', password='password')
    response = client.get(url)
    # print(response.content)
    print(type(response.content))
    assert response.status_code == 200
    assert 'Export is limited to 0 messages.' in smart_str(response.content)
    q = PyQuery(response.content)
    assert len(q('.export-link.disabled')) == 3
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?email_list=pubone'
    response = client.get(url)
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_export_limit_admin(admin_client, export_messages, settings, users):
    '''Limits do not apply to superuser'''
    settings.EXPORT_LIMIT = 0
    url = reverse('archive_browse_list', kwargs={'list_name': 'acme'})
    response = admin_client.get(url)
    print(type(response.content))
    assert response.status_code == 200
    assert 'Export is limited to 0 messages.' not in smart_str(response.content)
    q = PyQuery(response.content)
    assert len(q('.export-link.disabled')) == 0
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?email_list=acme'
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_export_bad_query(admin_client, messages, settings):
    settings.EXPORT_LIMIT = 0
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?q=%22pg59b2'
    response = admin_client.get(url, follow=True)
    print(type(response.content))
    assert response.status_code == 200
    assert 'Invalid search expression' in smart_str(response.content)


def test_help(client):
    url = reverse('archive_help')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_legacy_message(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist, legacy_number=1)
    url = reverse('archive_legacy_message', kwargs={'list_name': elist.name, 'id': '00001'})
    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert msg.get_absolute_url() in response.redirect_chain[0][0]


@pytest.mark.django_db(transaction=True)
def test_logout(admin_client):
    assert SESSION_KEY in admin_client.session
    url = reverse('archive_logout')
    response = admin_client.get(url, follow=True)
    assert response.status_code == 200
    assert SESSION_KEY not in admin_client.session


@pytest.mark.django_db(transaction=True)
def test_main(client):
    url = reverse('archive')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_search(client):
    # simple search
    url = reverse('archive_search') + '?q=database'
    response = client.get(url)
    assert response.status_code == 200
    # search with unicode (pi symbol)
    url = reverse('archive_search') + '?q=%CF%80'
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_reports_subscribers(client, users, subscribers):
    url = reverse('reports_subscribers')
    login_testing_unauthorized(client, url, username='unprivileged@example.com')
    response = client.get(url)
    assert response.status_code == 200
    # default date is last month
    date = datetime.date.today() - relativedelta(months=1)
    date = date.replace(day=1)
    assert response.context['date'] == date
    assert len(response.context['object_list']) == 2
    # month with data
    url = reverse('reports_subscribers') + '?date=2022-01-01'
    private = EmailListFactory.create(name='private', private=True)
    SubscriberFactory.create(email_list=private, date=datetime.date(2022, 1, 1))
    response = client.get(url)
    print(response.context)
    assert response.status_code == 200
    assert response.context['date'] == datetime.date(2022, 1, 1)
    object_list = response.context['object_list']
    assert len(object_list) == 1
    assert object_list.filter(email_list__private=True).count() == 0
    assert object_list.filter(email_list__private=False).count() > 0


@pytest.mark.django_db(transaction=True)
def test_reports_subscribers_csv(client, users, subscribers):
    url = reverse('reports_subscribers') + '?export=csv'
    login_testing_unauthorized(client, url, username='unprivileged@example.com')
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/csv'
    print(smart_str(response.content))
    assert 'pubone,5' in smart_str(response.content).splitlines()


@pytest.mark.django_db(transaction=True)
def test_reports_messages(client, users):
    date = datetime.datetime(2022, 2, 1, tzinfo=timezone.utc)
    elist = EmailListFactory.create(name='acme')
    _ = MessageFactory.create(email_list=elist, date=date)
    url = reverse('reports_messages') + '?start_date=2022-01-01&end_date=2022-12-31'
    login_testing_unauthorized(client, url, username='unprivileged@example.com')
    response = client.get(url)
    assert response.status_code == 200
    assert 'Total Messages: 1' in smart_str(response.content)
    q = PyQuery(response.content)
    rows = [c.text() for c in q('table tr td').items()]
    assert rows == ['acme', '1']


@pytest.mark.django_db(transaction=True)
def test_reports_messages_default(client, users):
    '''Test that report defaults to last month'''
    now = datetime.datetime.now(timezone.utc)
    elist = EmailListFactory.create(name='acme')
    # Create messages
    # Today
    _ = MessageFactory.create(email_list=elist, date=now)
    # two months ago
    xdate = now - relativedelta(months=2)
    _ = MessageFactory.create(email_list=elist, date=xdate)
    # last day of last month
    ydate = now.replace(day=1) - relativedelta(days=1)
    _ = MessageFactory.create(email_list=elist, date=ydate)
    # first day of last month
    zdate = ydate.replace(day=1)
    _ = MessageFactory.create(email_list=elist, date=zdate)
    # middle of last month
    adate = zdate + relativedelta(days=14)
    _ = MessageFactory.create(email_list=elist, date=adate)
    url = reverse('reports_messages')
    login_testing_unauthorized(client, url, username='unprivileged@example.com')
    response = client.get(url)
    assert response.status_code == 200
    assert 'Total Messages: 3' in smart_str(response.content)
    q = PyQuery(response.content)
    rows = [c.text() for c in q('table tr td').items()]
    assert rows == ['acme', '3']


@pytest.mark.django_db(transaction=True)
def test_reports_messages_csv(client, users):
    date = datetime.datetime(2022, 2, 1, tzinfo=timezone.utc)
    elist = EmailListFactory.create(name='acme')
    _ = MessageFactory.create(email_list=elist, date=date)
    url = reverse('reports_messages') + '?start_date=2022-01-01&end_date=2023-01-01&export=csv'
    login_testing_unauthorized(client, url, username='unprivileged@example.com')
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/csv'
    print(smart_str(response.content))
    assert 'acme,1' in smart_str(response.content).splitlines()


@pytest.mark.django_db(transaction=True)
def test_reports_messages_csv_no_date(client, users):
    '''Test that no date defaults to last month'''
    date = datetime.datetime.now(timezone.utc)
    date = date - relativedelta(months=1)
    elist = EmailListFactory.create(name='acme')
    _ = MessageFactory.create(email_list=elist, date=date)
    url = reverse('reports_messages') + '?export=csv'
    login_testing_unauthorized(client, url, username='unprivileged@example.com')
    response = client.get(url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/csv'
    print(smart_str(response.content))
    assert 'acme,1' in smart_str(response.content).splitlines()


@pytest.mark.django_db(transaction=True)
def test_redirect(client):
    Redirect.objects.create(old='/arch/msg/ietf/sssUEHOjoGhGRvDHFDrMP7h3Yf8/', new='/arch/msg/ietf/QajUS7jafu9sclZTiz4TMSehcjE/')
    url = reverse('archive_detail', kwargs={'list_name': 'ietf', 'id': 'sssUEHOjoGhGRvDHFDrMP7h3Yf8'})
    response = client.get(url)
    assert response.status_code == 301
    assert response['location'] == '/arch/msg/ietf/QajUS7jafu9sclZTiz4TMSehcjE/'


@pytest.mark.django_db(transaction=True)
def test_removed_message(client, thread_messages):
    msg = Message.objects.last()
    path = msg.get_file_path()
    assert os.path.exists(path)
    msg.delete()
    response = client.get(msg.get_absolute_url())
    assert response.status_code == 410
    assert 'This message has been removed' in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_message_download(client):
    listname = 'public'
    load_message('mail_normal.1', listname=listname)
    msg = Message.objects.first()
    url = reverse('archive_message_download', kwargs={'list_name': listname, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    assert response.content == msg.get_body_raw()


@pytest.mark.django_db(transaction=True)
def test_message_download_private(client):
    # test private message, no access
    elist = EmailListFactory.create(name='private', private=True)
    load_message('mail_normal.1', listname='private')
    msg = Message.objects.get(email_list__name='private')
    print(msg.email_list.private, msg.email_list.members.all())
    url = reverse('archive_message_download', kwargs={'list_name': 'private', 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 403
