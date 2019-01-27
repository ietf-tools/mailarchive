from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import os
import pytest
import xml.etree.ElementTree as ET

from factories import EmailListFactory, ThreadFactory, MessageFactory, UserFactory
from django.urls import reverse

from mlarchive.archive.models import EmailList, Message, Thread
from mlarchive.archive.signals import _get_lists_as_xml, get_purge_cache_urls


@pytest.mark.django_db(transaction=True)
def test_message_remove(client, thread_messages):
    message = Message.objects.first()
    path = message.get_file_path()
    removed_path = os.path.join(message.get_removed_dir(), message.hashcode)

    # ensure message file doesn't already exist in removed directory
    if os.path.exists(removed_path):
        os.remove(removed_path)

    assert os.path.exists(path)
    message.delete()
    assert not os.path.exists(path)
    assert os.path.exists(removed_path)


@pytest.mark.django_db(transaction=True)
def test_message_save(client):
    today = datetime.datetime.now().replace(second=0, microsecond=0)
    public = EmailListFactory.create(name='public', private=False)
    thread = ThreadFactory.create()
    MessageFactory.create(
        email_list=public,
        date=today,
        thread=thread)
    thread = Thread.objects.get(pk=thread.pk)
    assert thread.date == today


@pytest.mark.django_db(transaction=True)
def test_notify_new_list(client, tmpdir, settings):
    settings.EXPORT_DIR = str(tmpdir)
    EmailList.objects.create(name='dummy')
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    assert os.path.exists(path)
    with open(path) as file:
        assert 'dummy' in file.read()


@pytest.mark.django_db(transaction=True)
def test_get_lists_as_xml(client):
    private = EmailListFactory.create(name='private', private=True)
    EmailListFactory.create(name='public', private=False)
    user = UserFactory.create(username='test')
    private.members.add(user)
    xml = _get_lists_as_xml()
    root = ET.fromstring(xml)

    print(xml)

    public_anonymous = root.find("shared_root/[@name='public']").find("user/[@name='anonymous']")
    assert public_anonymous.attrib['access'] == 'read'

    private_anonymous = root.find("shared_root/[@name='private']").find("user/[@name='anonymous']")
    assert private_anonymous.attrib['access'] == 'none'

    private_test = root.find("shared_root/[@name='private']").find("user/[@name='test']")
    assert private_test.attrib['access'] == 'read,write'


@pytest.mark.django_db(transaction=True)
def test_get_purge_cache_urls(messages):
    message = messages.get(msgid='c02')
    urls = get_purge_cache_urls(message)
    assert urls
    print(urls)
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
