import mailbox
import pytest
import requests
from factories import EmailListFactory, UserFactory
from mock import patch
import os
import subprocess   # noqa


from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import AnonymousUser
from mlarchive.archive.utils import (get_noauth, get_lists, get_lists_for_user,
    lookup_user, process_members, get_membership, check_inactive, EmailList,
    create_mbox_file)


@pytest.mark.django_db(transaction=True)
def test_get_noauth():
    user = UserFactory.create(username='noauth')
    EmailListFactory.create(name='public')
    private1 = EmailListFactory.create(name='private1', private=True)
    EmailListFactory.create(name='private2', private=True)
    private1.members.add(user)
    lists = get_noauth(user)
    assert len(lists) == 1
    assert lists == [u'private2']


@pytest.mark.django_db(transaction=True)
def test_get_noauth_updates(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    user = UserFactory.create(username='noauth')
    public = EmailListFactory.create(name='public')
    private = EmailListFactory.create(name='private', private=True)
    private.members.add(user)

    if user.is_anonymous:
        user_id = 0
    else:
        user_id = user.id

    key = '{:04d}-noauth'.format(user_id)
    print "key {}:{}".format(key, cache.get(key))
    assert 'public' not in get_noauth(user)
    print "key {}:{}".format(key, cache.get(key))
    # assert cache.get(key) == []
    public.private = True
    public.save()
    assert 'public' in get_noauth(user)
    print "key {}:{}".format(key, cache.get(key))
    # assert False


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
    assert len(get_lists_for_user(admin_user)) == 3
    assert len(get_lists_for_user(anonymous)) == 1
    lists = get_lists_for_user(user1)
    assert private1 in lists
    assert private2 not in lists


@patch('requests.post')
def test_lookup_user(mock_post):
    response = requests.Response()
    # test error status
    response.status_code = 404
    mock_post.return_value = response
    user = lookup_user('joe@example.com')
    assert user is None
    # test no user object
    response.status_code = 200
    response._content = '{"person.person": {"1": {"user": ""}}}'
    user = lookup_user('joe@example.com')
    assert user is None
    # test success
    response._content = '{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    user = lookup_user('joe@example.com')
    assert user == 'joe@example.com'


@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_process_members(mock_post):
    response = requests.Response()
    response.status_code = 200
    response._content = '{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    mock_post.return_value = response
    email_list = EmailListFactory.create(name='private', private=True)
    assert email_list.members.count() == 0
    process_members(email_list, ['joe@example.com'])
    assert email_list.members.count() == 1
    assert email_list.members.get(username='joe@example.com')


@patch('subprocess.check_output')
@patch('requests.post')
@pytest.mark.django_db(transaction=True)
def test_get_membership(mock_post, mock_output):
    # setup
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    if os.path.exists(path):
        os.remove(path)

    private = EmailListFactory.create(name='private', private=True)
    # handle multiple calls to check_output
    mock_output.side_effect = ['private - Private Email List', 'joe@example.com']
    response = requests.Response()
    mock_post.return_value = response
    response.status_code = 200
    response._content = '{"person.person": {"1": {"user": {"username": "joe@example.com"}}}}'
    assert private.members.count() == 0
    options = DummyOptions()
    options.quiet = True
    get_membership(options, None)
    assert private.members.count() == 1
    assert private.members.first().username == 'joe@example.com'
    assert os.path.exists(path)


class DummyOptions(object):
    pass


@patch('mlarchive.archive.utils.input')
@patch('subprocess.check_output')
@pytest.mark.django_db(transaction=True)
def test_check_inactive(mock_output, mock_input):
    mock_input.return_value = 'n'
    EmailListFactory.create(name='public')
    EmailListFactory.create(name='acme')
    support = EmailListFactory.create(name='support')

    # handle multiple calls to check_output
    mock_output.side_effect = [
        'public - Public Email List',
        'acme-arch:  "|/usr/home/call-archives.py acme"',
        'public - Public Email List',
        'acme-arch:  "|/usr/home/call-archives.py acme"',
    ]
    assert EmailList.objects.filter(active=True).count() == 3

    check_inactive(prompt=True)
    assert EmailList.objects.filter(active=True).count() == 3

    check_inactive(prompt=False)
    assert EmailList.objects.filter(active=True).count() == 2
    assert EmailList.objects.filter(active=False).first() == support


@pytest.mark.django_db(transaction=True)
def test_create_mbox_file(tmpdir, settings, thread_messages):
    print 'tmpdir: {}'.format(tmpdir)
    settings.ARCHIVE_MBOX_DIR = str(tmpdir)
    elist = EmailList.objects.get(name='acme')    
    create_mbox_file(month=7, year=2016, elist=elist)
    path = os.path.join(settings.ARCHIVE_MBOX_DIR, 'public', elist.name, '2016-07.mail')
    assert os.path.exists(path)
    mbox = mailbox.mbox(path)
    assert len(mbox) == 4
    mbox.close()
