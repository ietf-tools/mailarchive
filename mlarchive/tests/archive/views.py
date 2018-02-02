import os
import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.urls import reverse
from factories import EmailListFactory, MessageFactory, UserFactory
from mlarchive.archive.models import Message
from mlarchive.archive.management.commands import _classes
from pyquery import PyQuery

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def load_message(filename, listname='public'):
    """Loads a message given path"""
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path) as f:
        data = f.read()
    _classes.archive_message(data, listname)

# --------------------------------------------------
# Tests
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_admin(client):
    "Admin Test"
    url = reverse('archive_admin')
    response = client.get(url)
    assert response.status_code == 403
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_admin_search_msgid(client, messages):
    msg = Message.objects.first()
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    url = reverse('archive_admin') + '?msgid=' + msg.msgid
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_subject(client, messages):
    msg = Message.objects.first()
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    url = reverse('archive_admin') + '?subject=message'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_date(client, messages):
    msg = Message.objects.first()
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    url = reverse('archive_admin') + '?start_date=' + msg.date.strftime("%Y-%m-%d")
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_search_list(client, messages):
    msg = Message.objects.first()
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    url = reverse('archive_admin') + '?email_list=' + msg.email_list.name
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [r.object for r in results]


@pytest.mark.django_db(transaction=True)
def test_admin_no_action(client, messages):
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    url = reverse('archive_admin')
    response = client.post(url, {'select-across': 0, 'index': 0})
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
def test_admin_console(client):
    url = reverse('archive_admin_console')
    response = client.get(url)
    assert response.status_code == 403
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_admin_guide(client):
    url = reverse('archive_admin_guide')
    response = client.get(url)
    assert response.status_code == 403
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    response = client.get(url)
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
def test_browse_redirect(client):
    url = reverse('archive_browse_redirect', kwargs={'list_name': 'pubone'})
    response = client.get(url)
    assert response.status_code == 302
    assert response['location'] == '/arch/search/?email_list=pubone'


@pytest.mark.django_db(transaction=True)
def test_browse_list(client, messages):
    url = reverse('archive_browse_list') + 'pubone'
    response = client.get(url)
    print url
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_browse_list_bogus_index(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&index={}'.format('x' * 27)
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_browse_query(client, messages):
    message = Message.objects.filter(email_list__name='pubone').order_by('-date').first()
    url = '%s/?email_list=pubone&index=%s' % (reverse('archive_search'), message.hashcode.strip('='))
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 4


@pytest.mark.django_db(transaction=True)
def test_browse_query_gbt(client, messages):
    messages = Message.objects.filter(email_list__name='apple').order_by('thread_order')
    message = messages.first()
    url = '%s/?email_list=apple&gbt=1&index=%s' % (reverse('archive_search'), message.hashcode.strip('='))
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 6

    # assert proper order
    print [(m.pk, m.thread_order) for m in messages]
    assert [r.object.pk for r in response.context['results']] == [m.pk for m in messages]


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

# def test_export(client):


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
def test_logout(client):
    UserFactory.create(is_superuser=True)
    assert client.login(username='admin', password='admin')
    assert SESSION_KEY in client.session
    url = reverse('archive_logout')
    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert SESSION_KEY not in client.session


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
