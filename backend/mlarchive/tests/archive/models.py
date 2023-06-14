import datetime
import email
import io
import pytest
from email import policy

from factories import EmailListFactory, ThreadFactory, MessageFactory
from django.urls import reverse
from django.utils.encoding import smart_str
from django.utils.http import urlencode
from mlarchive.archive.models import Message, Attachment, is_attachment, get_message_from_binary_file
from mlarchive.utils.test_utils import message_from_file, load_message
from mlarchive.utils.encoding import get_filename


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


@pytest.mark.skip(reason='2021-07-23: need to return to this issue')
@pytest.mark.django_db(transaction=True)
def test_message_get_body_html_urlize(client, urlize_messages):
    msg = Message.objects.get(msgid='urlize@example.com')
    body = msg.get_body_html()
    # test urlization of braces enclosed URL <https://www.ietf.org>
    print(body)
    assert '&lt;<a href="https://www.ietf.org" rel="nofollow">https://www.ietf.org</a>&gt;' in body


@pytest.mark.django_db(transaction=True)
def test_message_get_date_index_url(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist)
    assert msg.get_date_index_url() == '/arch/browse/public/?index={hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_pymsg(client):
    load_message('reply_to_url.mail')
    msg = Message.objects.first()
    print(msg.get_file_path())
    print(type(msg.pymsg))
    assert isinstance(msg.pymsg, email.message.EmailMessage)
    assert msg.pymsg.get('List-Post') == '<mailto:public@example.com>'


@pytest.mark.django_db(transaction=True)
def test_message_pymsg_error(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist)
    assert msg.pymsg_error == 'Error reading message file'


@pytest.mark.django_db(transaction=True)
def test_message_get_reply_url(client):
    load_message('reply_to_url.mail')
    msg = Message.objects.first()
    assert msg.get_reply_url() == 'mailto:public@example.com?subject=Re: This is a test'


@pytest.mark.django_db(transaction=True)
def test_message_get_thread_index_url(client):
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist)
    assert msg.get_thread_index_url() == '/arch/browse/public/?gbt=1&index={hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_static_date_index_url(client):
    date = datetime.datetime(2017, 4, 1)
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist, date=date)
    assert msg.get_static_date_index_url() == '/arch/browse/static/public/2017/#{hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_static_thread_index_url(client):
    date = datetime.datetime(2017, 4, 1)
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist, date=date)
    assert msg.get_static_thread_index_url() == '/arch/browse/static/public/thread/2017/#{hashcode}'.format(
        hashcode=msg.hashcode.strip('='))


@pytest.mark.django_db(transaction=True)
def test_message_get_from_line(client):
    '''Test that non-ascii text doesn't cause errors'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    msg.frm = 'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.from_line = ''
    msg.save()
    assert msg.get_from_line()

    msg.from_line = 'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.save()
    assert msg.get_from_line()


@pytest.mark.django_db(transaction=True)
def test_message_get_references(client):
    '''Test that message.get_references() returns reasonable
    data given variations of content'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)

    # typical contents
    msg.references = '<001-954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # no space separator
    msg.references = '<001-954@example.com><002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # alternate separator
    msg.references = '<001-954@example.com>\n\t<002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # extra whitespace
    msg.references = '<001- 954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    msg.references = '<001-954@example.com> <002-945@example\t.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # extra text
    msg.references = '[acme] durable goods <001-954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # truncated field
    msg.references = '<001-954@example.com> <002-945@exam'
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


@pytest.mark.django_db(transaction=True)
def test_thread_get_snippet(client):
    elist = EmailListFactory.create()
    message = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    assert message.thread.get_snippet()


@pytest.mark.django_db(transaction=True)
def test_attachment_get_sub_message(client, attachment_messages_no_index):
    attachment = Attachment.objects.first()
    sub = attachment.get_sub_message()
    assert sub.get_content_type() == 'text/plain'
    assert get_filename(sub) == 'skip32.c'
    print(type(sub.get_payload(decode=True)))
    assert 'unsigned' in smart_str(sub.get_payload(decode=True))


def test_is_attachment():
    msg = message_from_file('mail_multipart.1')
    parts = list(msg.walk())
    assert is_attachment(parts[0]) is False
    assert is_attachment(parts[1]) is False
    assert is_attachment(parts[2]) is True


def test_get_mail_from_binary_file():
    # test with problematic header
    b = b'''Date: Thu, 7 Nov 2013 17:54:55 +0000
    To: <joe@example.com>
    From: Bob <.bob@example.com>
    Subject: This is a test

    Testing.
    '''
    msg = get_message_from_binary_file(io.BytesIO(b), policy=policy.SMTP)
    assert isinstance(msg, email.message.Message)
    # test with clean header
    b = b'''Date: Thu, 7 Nov 2013 17:54:55 +0000
    To: <joe@example.com>
    From: Bob <bob@example.com>
    Subject: This is a test

    Testing.
    '''
    msg = get_message_from_binary_file(io.BytesIO(b), policy=policy.SMTP)
    assert isinstance(msg, email.message.EmailMessage)