from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import os
import pytest
import six

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.test import RequestFactory
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.encoding import smart_text
from factories import EmailListFactory, MessageFactory, UserFactory, AttachmentFactory
from mlarchive.archive.models import Message, Attachment
from mlarchive.archive.management.commands import _classes
from mlarchive.archive.views import (TimePeriod, add_nav_urls, is_small_year,
    add_one_month, get_this_next_periods, get_date_endpoints, get_thread_endpoints,
    DateStaticIndexView)
from pyquery import PyQuery


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def load_message(filename, listname='public'):
    """Loads a message given path"""
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path, 'rb') as f:
        data = f.read()
    _classes.archive_message(data, listname)


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
        datetime.datetime(2017,4,1),
        datetime.datetime(2017,5,1))
    time_period = TimePeriod(year=2017, month=None)
    assert get_this_next_periods(time_period) == (
        datetime.datetime(2017,1,1),
        datetime.datetime(2018,1,1))


@pytest.mark.django_db(transaction=True)
def test_add_one_month():
    date = datetime.datetime(2018,1,1)
    assert add_one_month(date) == datetime.datetime(2018,2,1)
    date = datetime.datetime(2018,12,1)
    assert add_one_month(date) == datetime.datetime(2019,1,1)


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
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_subject(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?subject=message'
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_date(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?start_date=' + msg.date.strftime("%Y-%m-%d")
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_list(admin_client, messages):
    msg = messages.first()
    url = reverse('archive_admin') + '?email_list=' + msg.email_list.name
    response = admin_client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_no_action(admin_client, messages):
    url = reverse('archive_admin')
    response = admin_client.post(url, {'select-across': 0, 'index': 0})
    assert response.status_code == 200


"""
@pytest.mark.django_db(transaction=True)
def test_admin_search_from(client,messages):
    msg = Message.objects.first()
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    realname, email_address = parseaddr(msg.frm)
    # test search email address portion
    url = reverse('archive_admin') + '?frm=' + email_address
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [ r.object for r in results ]
    # test search realname
"""


@pytest.mark.django_db(transaction=True)
def test_admin_menu(client, admin_client):
    url = reverse('archive')
    response = client.get(url)
    assert 'id="navbar-admin"' not in smart_text(response.content)
    response = admin_client.get(url)
    assert 'id="navbar-admin"' in smart_text(response.content)


@pytest.mark.django_db(transaction=True)
def test_admin_console(client, admin_client):
    url = reverse('archive_admin_console')
    response = client.get(url)
    assert response.status_code == 403
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
def test_browse_query(client, messages):
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'}) + '?q=invitation'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 2


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
    assert len(response.context['results']) == 4

    # assert proper order
    assert [r.msgid for r in response.context['results']] == ['a01', 'a02', 'a04', 'a03']


@pytest.mark.django_db(transaction=True)
def test_browse_index_gbt(client, messages):
    message = messages.get(msgid='a02')
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'}) + '?gbt=1&index={}'.format(message.hashcode.strip('='))
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 4


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
    assert msg.email_list.name in smart_text(response.content)


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
    today = datetime.datetime.today()
    elist = EmailListFactory.create(name='private', private=True)
    message = MessageFactory.create(email_list=elist, date=today)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': today.year})
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_browse_static_cache_headers_private(admin_client):
    '''Ensure private lists include Cache-Control: private header'''
    today = datetime.datetime.today()
    elist = EmailListFactory.create(name='private', private=True)
    message = MessageFactory.create(email_list=elist, date=today)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': '{}-{:02d}'.format(today.year, today.month)})
    response = admin_client.get(url)
    assert response.status_code == 200
    assert 'no-cache' in response.get('Cache-Control')


@pytest.mark.django_db(transaction=True)
def test_browse_static_cache_headers_public(client):
    '''Ensure private lists include Cache-Control: private header'''
    today = datetime.datetime.today()
    elist = EmailListFactory.create()
    message = MessageFactory.create(email_list=elist, date=today)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': today.year})
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
    assert 'http-equiv="refresh"' in smart_text(response.content)
    assert 'public/2015' in smart_text(response.content)


@pytest.mark.django_db(transaction=True)
def test_browse_static_small_year_current(client, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    today = datetime.datetime.today()
    current_year = today.year
    elist = EmailListFactory.create()
    message = MessageFactory.create(email_list=elist, date=today)
    url = reverse('archive_browse_static_date', kwargs={'list_name': elist.name, 'date': '{}-{:02d}'.format(today.year, today.month)})
    response = client.get(url)
    assert response.status_code == 200
    assert message.subject in smart_text(response.content)


@pytest.mark.django_db(transaction=True)
def test_browse_static_big_year_year(client, static_list, settings):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    url = reverse('archive_browse_static_date', kwargs={'list_name': static_list.name, 'date': '2017'})
    response = client.get(url)
    assert response.status_code == 200
    assert 'http-equiv="refresh"' in smart_text(response.content)
    assert 'public/2017-12' in smart_text(response.content)


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
    year = datetime.datetime.now().year
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
    assert 'unsigned' in smart_text(response.content)

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
    assert 'unsigned' in smart_text(response.content)


@pytest.mark.django_db(transaction=True)
def test_attachment_message_rfc822(client, attachment_messages_no_index):
    assert Attachment.objects.filter(content_type='message/rfc822').count() == 0


@pytest.mark.django_db(transaction=True)
def test_export(admin_client, thread_messages):
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?email_list=acme'
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response['Content-Disposition'].startswith('attachment;')
    assert response['Content-Type'] == 'application/x-tar-gz'


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
def test_export_limit(admin_client, messages, settings):
    settings.EXPORT_LIMIT = 0
    url = reverse('archive_browse_list', kwargs={'list_name': 'pubone'})
    response = admin_client.get(url)
    # print(response.content)
    print(type(response.content))
    assert response.status_code == 200
    assert 'Export is limited to 0 messages.' in smart_text(response.content)
    q = PyQuery(response.content)
    assert len(q('.export-link.disabled')) == 3
    url = reverse('archive_export', kwargs={'type': 'mbox'}) + '?email_list=pubone'
    response = admin_client.get(url)
    assert response.status_code == 302


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
