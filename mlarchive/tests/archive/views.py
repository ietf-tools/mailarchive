from email.utils import parseaddr

import pytest
from django.contrib.auth import SESSION_KEY
from django.urls import reverse
from factories import *
from mlarchive.archive.models import *
from mlarchive.archive.management.commands import _classes
from pyquery import PyQuery

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def load_message(filename,listname='public'):
    """Loads a message given path"""
    path = os.path.join(settings.BASE_DIR,'tests','data',filename)
    with open(path) as f:
        data = f.read()
    _classes.archive_message(data,listname)

# --------------------------------------------------
# Tests
# --------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_admin(client):
    "Admin Test"
    url = reverse('archive_admin')
    response = client.get(url)
    assert response.status_code == 403
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_admin_search_msgid(client, messages):
    msg = Message.objects.first()
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    url = reverse('archive_admin') + '?msgid=' + msg.msgid
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [ r.object for r in results ]

@pytest.mark.django_db(transaction=True)
def test_admin_search_subject(client,messages):
    msg = Message.objects.first()
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    url = reverse('archive_admin') + '?subject=' + msg.subject.split()[0]
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [ r.object for r in results ]

@pytest.mark.django_db(transaction=True)
def test_admin_search_date(client,messages):
    msg = Message.objects.first()
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    url = reverse('archive_admin') + '?start_date=' + msg.date.strftime("%Y-%m-%d")
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [ r.object for r in results ]

@pytest.mark.django_db(transaction=True)
def test_admin_search_list(client,messages):
    msg = Message.objects.first()
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    url = reverse('archive_admin') + '?email_list=' + str(msg.email_list.pk)
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert msg in [ r.object for r in results ]

@pytest.mark.django_db(transaction=True)
def test_admin_no_action(client,messages):
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    url = reverse('archive_admin')
    response = client.post(url,{'select-across':0,'index':0})
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
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_admin_guide(client):
    url = reverse('archive_admin_guide')
    response = client.get(url)
    assert response.status_code == 403
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_advsearch(client):
    url = reverse('archive_advsearch')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_browse(client):
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_detail(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('archive_detail', kwargs={'list_name':elist.name,'id':msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_detail_content_link(client):
    '''Test that url in message content appears as a link'''
    listname = 'public'
    load_message('mail_with_url.1',listname=listname)
    msg = Message.objects.first()
    url = reverse('archive_detail', kwargs={'list_name':listname,'id':msg.hashcode})
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
    user = UserFactory.create(is_staff=True)
    url = reverse('archive_detail', kwargs={'list_name':elist.name,'id':msg.hashcode})
    # not logged in
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#admin-link')) == 0
    # priviledged user
    client.login(username='admin',password='admin')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#admin-link')) == 1

#def test_export(client):

def test_help(client):
    url = reverse('archive_help')
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_legacy_message(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist,legacy_number=1)
    url = reverse('archive_legacy_message', kwargs={'list_name':elist.name,'id':'00001'})
    response = client.get(url, follow=True)
    assert response.status_code == 200
    assert msg.get_absolute_url() in response.redirect_chain[0][0]

@pytest.mark.django_db(transaction=True)
def test_logout(client):
    user = UserFactory.create(is_superuser=True)
    assert client.login(username='admin',password='admin')
    assert SESSION_KEY in client.session
    url = reverse('archive_logout')
    response = client.get(url,follow=True)
    assert response.status_code == 200
    assert not SESSION_KEY in client.session

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
