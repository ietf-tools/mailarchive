"""Tests for the browser-facing JSON API (mlarchive.archive.web_api).

These mirror the conventions of the other view/api tests: they use the
shared fixtures from conftest (``messages`` loads sample lists + builds the
Elasticsearch index, so the search/lists tests require the ES service the
devcontainer provides).
"""
import pytest

from django.urls import reverse

from factories import EmailListFactory, MessageFactory, UserFactory
from mlarchive.archive.models import User


# ------------------------------
# whoami
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_whoami_anonymous(client):
    response = client.get(reverse('web_api_whoami'))
    assert response.status_code == 200
    data = response.json()
    assert data['authenticated'] is False
    assert data['username'] == ''


@pytest.mark.django_db(transaction=True)
def test_whoami_authenticated(client):
    user = UserFactory(username='someone@example.com')
    client.force_login(user)
    response = client.get(reverse('web_api_whoami'))
    data = response.json()
    assert data['authenticated'] is True
    assert data['username'] == 'someone@example.com'


# ------------------------------
# lists
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_lists_anonymous_excludes_private(client, messages):
    response = client.get(reverse('web_api_lists'))
    assert response.status_code == 200
    data = response.json()
    names = {row['name']: row for row in data['lists']}
    # public lists present with message counts
    assert 'pubone' in names
    assert names['pubone']['message_count'] == 5
    assert names['pubone']['private'] is False
    # private lists excluded for anonymous users
    assert 'private' not in names
    assert 'private-ops' not in names


@pytest.mark.django_db(transaction=True)
def test_lists_member_sees_their_private_list(client, messages):
    user = User.objects.get(username='private_user')
    client.force_login(user)
    data = client.get(reverse('web_api_lists')).json()
    names = {row['name'] for row in data['lists']}
    assert 'private' in names           # member of this list
    assert 'private-ops' not in names   # not a member


# ------------------------------
# search
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_search_by_list(client, messages):
    url = reverse('web_api_search') + '?email_list=pubone'
    data = client.get(url).json()
    assert data['count'] == 5
    assert len(data['results']) == 5
    assert all(r['email_list'] == 'pubone' for r in data['results'])
    # facets present
    assert 'list_terms' in data['aggregations']
    # result carries the permalink and serialized fields
    assert all(r['url'] for r in data['results'])


@pytest.mark.django_db(transaction=True)
def test_search_pagination(client, messages):
    # pubthree has 21 messages, results_per_page is 20 in test settings
    url = reverse('web_api_search') + '?email_list=pubthree'
    data = client.get(url).json()
    assert data['count'] == 21
    assert data['num_pages'] == 2
    assert data['has_next'] is True
    assert data['has_previous'] is False
    assert len(data['results']) == 20


@pytest.mark.django_db(transaction=True)
def test_search_private_excluded_for_anonymous(client, messages):
    url = reverse('web_api_search') + '?email_list=private'
    data = client.get(url).json()
    assert data['count'] == 0
    assert data['results'] == []


@pytest.mark.django_db(transaction=True)
def test_search_private_visible_to_member(client, messages):
    user = User.objects.get(username='private_user')
    client.force_login(user)
    url = reverse('web_api_search') + '?email_list=private'
    data = client.get(url).json()
    assert data['count'] == 2
    assert all(r['email_list'] == 'private' for r in data['results'])


# ------------------------------
# message detail
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_message_detail_public(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('web_api_message_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['msgid'] == msg.msgid
    assert data['subject'] == msg.subject
    assert data['email_list'] == elist.name
    assert data['url'] == msg.get_absolute_url()
    # nav block and rendered HTML fields are present
    assert set(data['nav']) == {
        'previous_in_list', 'next_in_list', 'previous_in_thread', 'next_in_thread'}
    assert 'body' in data
    assert 'thread_snippet' in data


@pytest.mark.django_db(transaction=True)
def test_message_detail_unpadded_hashcode(client):
    """A permalink without the trailing '=' padding still resolves (pad_id)."""
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('web_api_message_detail',
                  kwargs={'list_name': elist.name, 'id': msg.hashcode.rstrip('=')})
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()['msgid'] == msg.msgid


@pytest.mark.django_db(transaction=True)
def test_message_detail_private_denied_anonymous(client):
    elist = EmailListFactory.create(name='secret', private=True)
    msg = MessageFactory.create(email_list=elist)
    url = reverse('web_api_message_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_message_detail_private_allowed_for_member(client):
    elist = EmailListFactory.create(name='secret', private=True)
    msg = MessageFactory.create(email_list=elist)
    user = UserFactory(username='member@example.com')
    elist.members.add(user)
    client.force_login(user)
    url = reverse('web_api_message_detail', kwargs={'list_name': elist.name, 'id': msg.hashcode})
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()['msgid'] == msg.msgid
