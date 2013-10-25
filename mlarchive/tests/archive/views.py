import pytest
from django.core.urlresolvers import reverse
from mlarchive.archive.models import *

def test_main(client):
    url = reverse('archive')
    response = client.get(url)
    assert response.status_code == 200

#@pytest.mark.django_db
#def test_browse(client):
#    url = reverse('archive_browse')
#    response = client.get(url)
#    assert response.status_code == 200

def test_advsearch(client):
    url = reverse('archive_advsearch')
    response = client.get(url)
    assert response.status_code == 200

def test_admin(client):
    "Admin Test"
    url = reverse('archive_admin')
    response = client.get(url)
    assert response.status_code == 403

@pytest.mark.django_db
def test_dummy(client):
    count = Message.objects.all().count()
    assert count == 0
