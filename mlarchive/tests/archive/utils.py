import datetime
import os
import pytest
from factories import EmailListFactory, UserFactory, MessageFactory, ThreadFactory

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from mlarchive.archive.utils import get_noauth, get_lists, get_lists_for_user, get_purge_cache_urls
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
def test_get_purge_cache_urls(messages):
    message = messages.get(msgid='c02')
    urls = get_purge_cache_urls(message)
    assert urls
    print urls
    # previous in list
    msg = messages.get(msgid='c01')
    assert msg.get_absolute_url_with_host() in urls
    # next in list
    msg = messages.get(msgid='c03')
    assert msg.get_absolute_url_with_host() in urls
    # thread mate
    msg = messages.get(msgid='c04')
    assert msg.get_absolute_url_with_host() in urls
    # date index page
    index_urls = message.get_absolute_static_index_urls()
    assert index_urls[0] in urls
    # thread index page
    assert index_urls[1] in urls
    # self on create
    assert message.get_absolute_url_with_host() not in urls
    # self on delete
    urls = get_purge_cache_urls(message, created=False)
    assert message.get_absolute_url_with_host() in urls