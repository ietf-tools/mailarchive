import pytest
from django.core.urlresolvers import reverse
from mlarchive.archive.models import *
from pyquery import PyQuery

def test_admin(client):
    "Admin Test"
    url = reverse('archive_admin')
    response = client.get(url)
    assert response.status_code == 403

#def test_admin_console(client):

#def test_admin_guide(client):

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

#def test_logout(client):

def test_main(client):
    url = reverse('archive')
    response = client.get(url)
    assert response.status_code == 200