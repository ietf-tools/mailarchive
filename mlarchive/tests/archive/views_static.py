import pytest
import datetime
import os

from pyquery import PyQuery
from factories import EmailListFactory, MessageFactory, ThreadFactory
from mlarchive.archive.views_static import (rebuild_static_index,
    link_index_page, build_static_pages, is_small_year)


"""
@pytest.mark.django_db(transaction=True)
def test_rebuild_static_index(static_list):
    rebuild_static_index(static_list)
    assert True


@pytest.mark.django_db(transaction=True)
def test_build_static_pages(static_list, settings, static_dir):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    build_static_pages(static_list)
    path = os.path.join(static_dir, static_list.name)
    assert '2017.html' in os.listdir(path)


@pytest.mark.django_db(transaction=True)
def test_link_index_page(static_list, settings, static_dir):
    settings.STATIC_INDEX_YEAR_MINIMUM = 20
    build_static_pages(static_list)
    link_index_page(static_list)
    path = os.path.join(static_dir, static_list.name)
    assert 'index.html' in os.listdir(path)
    assert 'thread.html' in os.listdir(path)


@pytest.mark.django_db(transaction=True)
def test_write_index():
    assert True


@pytest.mark.django_db(transaction=True)
def test_update_static_index_thread(static_list, settings):
    settings.STATIC_INDEX_MESSAGES_PER_PAGE = 10
    today = datetime.datetime.today()
    old_thread = static_list.thread_set.filter(date__year=2015).first()
    rebuild_static_index()
    files = os.listdir(os.path.join(settings.STATIC_INDEX_DIR, 'public'))
    MessageFactory.create(email_list=static_list, subject="tribulations", date=today, thread=old_thread)
    update_static_index(static_list)
    path = os.path.join(settings.STATIC_INDEX_DIR, static_list.name, '2015.html')
    with open(path) as f:
        data = f.read()
    assert 'tribulations' in data


@pytest.mark.django_db(transaction=True)
def test_update_static_index_date(static_list, settings):
    settings.STATIC_INDEX_MESSAGES_PER_PAGE = 10
    date = datetime.datetime(2017,5,1)
    rebuild_static_index()
    MessageFactory.create(email_list=static_list, subject="tribulations", date=date)
    update_static_index(static_list)
    path = os.path.join(settings.STATIC_INDEX_DIR, static_list.name, '2017-05.html' )
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
"""
