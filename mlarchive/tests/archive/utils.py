import os
import pytest
from factories import EmailListFactory, UserFactory

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from mlarchive.archive.utils import get_noauth, get_lists, get_lists_for_user, rebuild_static_index
from mlarchive.utils.test_utils import get_request


@pytest.mark.django_db(transaction=True)
def test_get_noauth():
    user = UserFactory.create(username='noauth')
    EmailListFactory.create(name='public')
    private1 = EmailListFactory.create(name='private1', private=True)
    EmailListFactory.create(name='private2', private=True)
    private1.members.add(user)
    factory = RequestFactory()
    request = factory.get('/arch/search/?q=dummy')
    request.user = user
    setattr(request, 'session', {})
    lists = get_noauth(request)
    assert len(lists) == 1
    assert lists == [u'private2']


@pytest.mark.django_db(transaction=True)
def test_get_lists():
    EmailListFactory.create(name='pubone')
    assert 'pubone' in get_lists()


@pytest.mark.django_db(transaction=True)
def test_get_lists_for_user(admin_user):
    EmailListFactory.create(name='public')
    private1 = EmailListFactory.create(name='private1', private=True)
    private2 = EmailListFactory.create(name='private2', private=True)
    user1 = UserFactory.create(username='user1')
    private1.members.add(user1)
    anonymous = AnonymousUser()
    assert len(get_lists_for_user(get_request(user=admin_user))) == 3
    assert len(get_lists_for_user(get_request(user=anonymous))) == 1
    lists = get_lists_for_user(get_request(user=user1))
    assert private1 in lists
    assert private2 not in lists


@pytest.mark.django_db(transaction=True)
def test_rebuild_static_index(messages):
    rebuild_static_index()
    assert 'pubone' in os.listdir(settings.STATIC_INDEX_DIR)
    assert 'index.html' in os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'pubone'))
    assert 'maillist.html' in os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'pubone'))
