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
    assert client.login(username='test-chair',password='ietf-test')
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
    user = UserFactory.create(username='test-chair')
    elist.members.add(user)
    assert client.login(username='test-chair',password='ietf-test')
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
    
    

