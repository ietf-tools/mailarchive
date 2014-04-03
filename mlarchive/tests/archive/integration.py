import pytest
import sys

from django.core.urlresolvers import reverse
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

def test_not_logged_search(client):
    'Test that a not logged in user does not see private lists in search results'
    # check results and filters
    pass

def test_unauthorized_ajax_request(client):
    'Test that'
    pass

def test_admin_access(client):
    'Test that only superusers see admin link and have access to admin pages'
    pass

def test_console_access(client):
    'Test that only superusers have access to console page'
    url = reverse('archive_browse')
    pass

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
    url = reverse('archive_search') + '?q=msgid:000@amsl.com'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_queries_spam_score_field(client,messages):
    url = reverse('archive_search') + '?q=spam_score:1'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1>>>>>>> .r323
