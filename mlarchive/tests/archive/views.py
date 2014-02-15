import pytest
from django.contrib.auth import SESSION_KEY
from django.core.urlresolvers import reverse
from factories import *
from mlarchive.archive.models import *
from pyquery import PyQuery

@pytest.mark.django_db(transaction=True)
def test_admin(client):
    "Admin Test"
    url = reverse('archive_admin')
    response = client.get(url)
    assert response.status_code == 403
    user = UserFactory.create(username='test-chair',is_superuser=True)
    assert client.login(username='test-chair',password='ietf-test')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_admin_console(client):
    url = reverse('archive_admin_console')
    response = client.get(url)
    assert response.status_code == 403
    user = UserFactory.create(username='test-chair',is_superuser=True)
    assert client.login(username='test-chair',password='ietf-test')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_admin_guide(client):
    url = reverse('archive_admin_guide')
    response = client.get(url)
    assert response.status_code == 403
    user = UserFactory.create(username='test-chair',is_superuser=True)
    assert client.login(username='test-chair',password='ietf-test')
    response = client.get(url)
    assert response.status_code == 200

def test_advsearch(client):
    url = reverse('archive_advsearch')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_browse(client):
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200

#def test_detail(client):

#def test_export(client):

@pytest.mark.django_db(transaction=True)
def test_logout(client):
    user = UserFactory.create(username='test-chair')
    assert client.login(username='test-chair',password='ietf-test')
    assert SESSION_KEY in client.session
    url = reverse('archive_logout')
    response = client.get(url,follow=True)
    assert response.status_code == 200
    assert not SESSION_KEY in client.session

def test_main(client):
    url = reverse('archive')
    response = client.get(url)
    assert response.status_code == 200