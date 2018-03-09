import pytest
import datetime
import os

from django.conf import settings
from factories import EmailListFactory, MessageFactory, ThreadFactory
from mlarchive.archive.models import EmailList
from mlarchive.archive.views_static import rebuild_static_index, update_static_index, build_msg_pages


@pytest.mark.django_db(transaction=True)
def test_rebuild_static_index(messages):
    rebuild_static_index()
    assert 'pubone' in os.listdir(settings.STATIC_INDEX_DIR)
    assert 'index.html' in os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'pubone'))
    assert 'maillist.html' in os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'pubone'))
    assert 'threadlist.html' in os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'pubone'))


@pytest.mark.django_db(transaction=True)
def test_update_static_index_thread(settings):
    settings.STATIC_INDEX_MESSAGES_PER_PAGE = 10
    today = datetime.datetime.today()
    public = EmailListFactory.create(name='public')
    date = datetime.datetime(2013, 2, 1)
    old_thread = ThreadFactory.create(date=date)
    MessageFactory.create(email_list=public, date=date, thread=old_thread)
    for num in xrange(35):
        MessageFactory.create(email_list=public, date=today - datetime.timedelta(days=num))
    rebuild_static_index()
    files = os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'public'))
    assert 'threadlist.html' in files
    assert 'thread0001.html' in files
    MessageFactory.create(email_list=public, subject="tribulations", date=today, thread=old_thread)
    update_static_index(public)
    path = os.path.join(settings.STATIC_INDEX_DIR, 'public', 'thread0001.html')
    with open(path) as f:
        data = f.read()
    assert 'tribulations' in data


@pytest.mark.django_db(transaction=True)
def test_update_static_index_date(settings):
    settings.STATIC_INDEX_MESSAGES_PER_PAGE = 10
    today = datetime.datetime.today()
    public = EmailListFactory.create(name='public')
    for num in xrange(35):
        MessageFactory.create(email_list=public, date=today - datetime.timedelta(days=num))
    rebuild_static_index()
    files = os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'public'))
    assert 'maillist.html' in files
    assert 'mail0001.html' in files
    MessageFactory.create(email_list=public, subject="tribulations", date=today - datetime.timedelta(days=10))
    update_static_index(public)
    path = os.path.join(settings.STATIC_INDEX_DIR, 'public', 'mail0003.html')
    with open(path) as f:
        data = f.read()
    assert 'tribulations' in data


@pytest.mark.django_db(transaction=True)
def test_build_msg_pages(messages, static_dir):
    email_list = EmailList.objects.get(name='pubone')
    message = messages.filter(email_list=email_list).first()
    build_msg_pages(email_list)
    assert 'pubone' in os.listdir(settings.STATIC_INDEX_DIR)
    assert message.hashcode.strip('=') + '.html' in os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'pubone'))
