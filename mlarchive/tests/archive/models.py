import datetime
import pytest

from factories import EmailListFactory, ThreadFactory, MessageFactory
from django.urls import reverse
from django.utils.http import urlencode
from mlarchive.archive.models import Message


@pytest.mark.django_db(transaction=True)
def test_message_frm_name(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist, frm='John Smith <jsmith@example.com')
    assert msg.frm_name == 'John Smith'


@pytest.mark.django_db(transaction=True)
def test_message_frm_name_no_realname(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist, frm='jsmith@example.com')
    assert msg.frm_name == 'jsmith'


@pytest.mark.django_db(transaction=True)
def test_message_get_admin_url(client):
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    url = reverse('archive_admin') + '?' + urlencode(dict(msgid=msg.msgid))
    assert msg.get_admin_url() == url


@pytest.mark.django_db(transaction=True)
def test_message_get_date_index_url(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist, date_index_page='mail0001.html')
    assert msg.get_date_index_url() == '/arch/browse/public/?index={hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_thread_index_url(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist, thread_index_page='thread0001.html')
    assert msg.get_thread_index_url() == '/arch/browse/public/?gbt=1&index={hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_static_date_index_url(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist, date_index_page='mail0001.html')
    assert msg.get_static_date_index_url() == '/arch/browse/public/mail0001.html#{hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_static_thread_index_url(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist, thread_index_page='thread0001.html')
    assert msg.get_static_thread_index_url() == '/arch/browse/public/thread0001.html#{hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_from_line(client):
    '''Test that non-ascii text doesn't cause errors'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    msg.frm = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.from_line = ''
    msg.save()
    assert msg.get_from_line()

    msg.from_line = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.save()
    assert msg.get_from_line()


@pytest.mark.django_db(transaction=True)
def test_message_get_references(client):
    '''Test that message.get_references() returns reasonable
    data given variations of content'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)

    # typical contents
    msg.references = u'<001-954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # no space separator
    msg.references = u'<001-954@example.com><002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # alternate separator
    msg.references = u'<001-954@example.com>\n\t<002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # extra whitespace
    msg.references = u'<001- 954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    msg.references = u'<001-954@example.com> <002-945@example\t.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # extra text
    msg.references = u'[acme] durable goods <001-954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # truncated field
    msg.references = u'<001-954@example.com> <002-945@exam'
    msg.save()
    expected = ['001-954@example.com']
    assert msg.get_references() == expected

    # duplicated references
    msg.references = ' '.join([
        '<000@example.com>',
        '<001@example.com>',
        '<000@example.com>',
        '<001@example.com>',
        '<002@example.com>'])
    msg.save()
    expected = ['000@example.com', '001@example.com', '002@example.com']
    assert msg.get_references() == expected


@pytest.mark.django_db(transaction=True)
def test_thread_get_snippet(client):
    elist = EmailListFactory.create()
    message = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    assert message.thread.get_snippet()


@pytest.mark.django_db(transaction=True)
def test_message_get_thread_snippet(client):
    elist = EmailListFactory.create()
    message = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    assert message.get_thread_snippet()


@pytest.mark.django_db(transaction=True)
def test_message_next_in_list(client):
    '''Test that message.next_in_list returns the next message in the
    list, ordered by date'''
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 2))
    assert Message.objects.count() == 2
    assert message1.next_in_list() == message2


@pytest.mark.django_db(transaction=True)
def test_message_next_in_thread(client):
    '''Test that message.next_in_thread returns the next message in the
    thread'''
    elist = EmailListFactory.create()
    thread = ThreadFactory.create(email_list=elist)
    message1 = MessageFactory.create(
        email_list=elist,
        thread=thread,
        thread_order=1,
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        thread=thread,
        thread_order=2,
        date=datetime.datetime(2016, 1, 2))
    assert Message.objects.count() == 2
    assert message1.next_in_thread() == message2


@pytest.mark.django_db(transaction=True)
def test_message_previous_in_list(client):
    '''Test that message.previous_in_list returns the previous message in the
    list, ordered by date'''
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 2))
    assert Message.objects.count() == 2
    assert message2.previous_in_list() == message1


@pytest.mark.django_db(transaction=True)
def test_message_previous_in_thread_same_thread(client):
    '''Test that message.next_in_thread returns the next message in the
    thread'''
    elist = EmailListFactory.create()
    thread = ThreadFactory.create(email_list=elist)
    message1 = MessageFactory.create(
        email_list=elist,
        thread=thread,
        thread_order=1,
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        thread=thread,
        thread_order=2,
        date=datetime.datetime(2016, 1, 2))
    assert Message.objects.count() == 2
    assert message2.previous_in_thread() == message1


@pytest.mark.django_db(transaction=True)
def test_message_previous_in_thread_different_thread(client):
    '''Test that message.next_in_thread returns the next message in the
    thread'''
    elist = EmailListFactory.create()
    thread1 = ThreadFactory.create(date=datetime.datetime(2016, 1, 1), email_list=elist)
    thread2 = ThreadFactory.create(date=datetime.datetime(2016, 1, 10), email_list=elist)
    message1 = MessageFactory.create(
        email_list=elist,
        thread=thread1,
        thread_order=1,
        date=datetime.datetime(2016, 1, 1))
    MessageFactory.create(
        email_list=elist,
        thread=thread1,
        thread_order=2,
        date=datetime.datetime(2016, 1, 2))
    message3 = MessageFactory.create(
        email_list=elist,
        thread=thread2,
        thread_order=1,
        date=datetime.datetime(2016, 1, 10))
    assert Message.objects.count() == 3
    assert thread1.first == message1
    assert message3.previous_in_thread() == message1
