import pytest
import sys

from django.urls import reverse
from factories import *
from mlarchive.archive.models import *
from pyquery import PyQuery

# --------------------------------------------------
# Authentication
# --------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_not_logged_browse(client):
    'Test that a not logged in user does not see any private lists in browse menu'
    elist = EmailListFactory.create(name='private',private=True)
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#private-lists li')) == 0

@pytest.mark.django_db(transaction=True)
def test_unauth_browse(client):
    '''Test that a logged in user does not see private lists they aren't
    a member of.
    '''
    elist = EmailListFactory.create(name='private',private=True)
    user = UserFactory.create()
    assert client.login(username='admin',password='admin')
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#private-lists li')) == 0

@pytest.mark.django_db(transaction=True)
def test_auth_browse(client):
    '''Test that a logged in user does see private lists they are
    a member of.
    '''
    elist = EmailListFactory.create(name='private',private=True)
    user = UserFactory.create()
    assert client.login(username='admin',password='admin')
    elist.members.add(user)
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#private-lists li')) == 1

@pytest.mark.django_db(transaction=True)
def test_not_logged_search(client,messages):
    '''Test that a not logged in user does not see private lists in search results'''
    url = reverse('archive_search') + '?email_list=private'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 0

@pytest.mark.django_db(transaction=True)
def test_unauth_search(client,messages):
    """Test that a logged in user does not see results from private lists they aren't a member of"""
    user = UserFactory.create(username='dummy')
    assert client.login(username='dummy',password='admin')
    url = reverse('archive_search') + '?email_list=private'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 0

@pytest.mark.django_db(transaction=True)
def test_admin_access(client):
    '''Test that only superusers see admin link and have access to admin pages'''
    url = reverse('archive')
    # anonymous user
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('a[href="/arch/admin"]')) == 0
    # admin user
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('a[href="/arch/admin/"]')) == 1

@pytest.mark.django_db(transaction=True)
def test_console_access(client):
    '''Test that only superusers have access to console page'''
    url = reverse('archive_admin_console')
    # anonymous user
    response = client.get(url)
    assert response.status_code == 403
    # admin user
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    response = client.get(url)
    assert response.status_code == 200

# --------------------------------------------------
# Queries
# --------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_odd_queries(client):
    'Test some odd queries'
    url = reverse('archive_search')
    url = url + '?q=-'
    print url
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_queries_bad_qid(client,messages):
    'Test malicious query'
    message = Message.objects.first()
    url = message.get_absolute_url() + "/%3fqid%3ddf6d7ccfedface723ffb184a6f52bab3'+order+by+1+--+;"
    response = client.get(url)
    assert response.status_code == 404

@pytest.mark.django_db(transaction=True)
def test_queries_sort_from(client,messages):
    url = reverse('archive_search') + '?email_list=pubthree&so=frm'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert results[0].object.frm <= results[1].object.frm

@pytest.mark.django_db(transaction=True)
def test_queries_to_field(client,messages):
    url = reverse('archive_search') + '?q=to:to@amsl.com'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_queries_from_field(client,messages):
    url = reverse('archive_search') + '?q=from:larry@amsl.com'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_queries_subject_field(client,messages):
    url = reverse('archive_search') + '?q=subject:BBQ'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_queries_msgid_field(client,messages):
    msgid = Message.objects.first().msgid
    #url = reverse('archive_search') + '?q=msgid:000@amsl.com'
    url = reverse('archive_search') + '?q=msgid:{}'.format(msgid)
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    #print '%s' % ([ x.msgid for x in response.context['results'] ])
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_queries_spam_score_field(client,messages):
    url = reverse('archive_search') + '?q=spam_score:1'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_queries_pagination(client,messages):
    # verify pre-conditions
    message_count = Message.objects.filter(email_list__name='pubthree').count()
    assert message_count == 21
    # test page=2
    url = reverse('archive_search') + '?email_list=pubthree&page=2'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 1
    
@pytest.mark.django_db(transaction=True)
def test_queries_pagination_bogus(client,messages):
    # verify pre-conditions
    message_count = Message.objects.filter(email_list__name='pubthree').count()
    assert message_count == 21
    # test non integer
    url = reverse('archive_search') + '?email_list=pubthree&page=bogus'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 20   # should get page 1
    # test page too high
    url = reverse('archive_search') + '?email_list=pubthree&page=1000'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 1    # should get last page

