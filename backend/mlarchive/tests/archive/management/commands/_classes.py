from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import email
import glob
import io
import mailbox
import os
import pytest
import pytz
import shutil
import six
import sys

from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from mlarchive.archive.models import Message, EmailList
from mlarchive.archive.management.commands._classes import (archive_message, clean_spaces, MessageWrapper,
    get_base_subject, get_envelope_date, tzoffset, get_from, get_header_date, get_mb,
    is_aware, get_received_date, parsedate_to_datetime, subject_is_reply, lookup_extension)
from factories import EmailListFactory, MessageFactory, ThreadFactory
from mlarchive.utils.test_utils import message_from_file


# for Python 2/3 compatability
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


def teardown_module(module):
    if os.path.exists(settings.LOG_FILE):
        os.remove(settings.LOG_FILE)
    content = StringIO()
    call_command('clear_index', interactive=False, stdout=content)


@pytest.mark.django_db(transaction=True)
def test_archive_message(client):
    data = '''From: Joe <joe@example.com>
To: Joe <joe@example.com>
Date: Thu, 7 Nov 2013 17:54:55 +0000
Message-ID: <0000000002@example.com>
Content-Type: text/plain; charset="us-ascii"
Subject: This is a test

Hello,

This is a test email.  database
'''
    data = data.encode('ASCII')
    status = archive_message(data, 'test', private=False)
    assert status == 0
    # ensure message in db
    assert Message.objects.all().count() == 1
    # ensure message in index
    url = '%s?q=database' % reverse('archive_search')
    response = client.get(url)
    assert len(response.context['results']) == 1
    # ensure message on disk
    # TODO
    # test that thread date is correct in index
    url = reverse('archive_search') + '?q=tdate:20131107175455'
    assert len(response.context['results']) == 1


@pytest.mark.django_db(transaction=True)
def test_archive_message_fail(client):
    data = b'Hello,\n This is a test email.  With no headers.'
    # remove any existing failed messages
    publist = EmailListFactory.create(name='public')
    shutil.rmtree(publist.failed_dir, ignore_errors=True)

    status = archive_message(data, 'public', private=False)
    assert status == 1
    assert Message.objects.all().count() == 0
    filename = os.path.join(publist.failed_dir, datetime.datetime.today().strftime('%Y-%m-%d') + '.0000')
    assert os.path.exists(filename)
    os.remove(filename)                         # cleanup


def test_archive_message_bad_order():
    # test that index thread id / date correct if older message added later
    # TODO
    pass


@pytest.mark.django_db(transaction=True)
def test_archive_message_change_list_access(messages):
    data = '''From: Joe <joe@example.com>
To: Joe <joe@example.com>
Date: Thu, 7 Nov 2013 17:54:55 +0000
Message-ID: <0000000002@example.com>
Content-Type: text/plain; charset="us-ascii"
Subject: This is a test

Hello,

This is a test email.  database
'''
    data = data.encode('ASCII')
    email_list = EmailList.objects.get(name='pubone')
    assert email_list.private is False
    status = archive_message(data, 'pubone', private=True)
    assert status == 0
    email_list = EmailList.objects.get(name='pubone')
    assert email_list.private is True
    # remove message from index
    # TODO figure out better test index management
    message = Message.objects.get(msgid='0000000002@example.com')
    message.delete()


@pytest.mark.django_db(transaction=True)
def test_archive_message_encoded_word(client):
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'encoded_word.mail')
    with open(path, 'rb') as f:
        data = f.read()
    status = archive_message(data, 'test', private=False)
    assert status == 0
    # ensure message in db
    assert Message.objects.all().count() == 1
    # ensure message in index
    url = '%s?q=encoded' % reverse('archive_search')
    response = client.get(url)
    assert len(response.context['results']) == 1
    message = Message.objects.first()
    assert message.frm == 'J\xe4rvinen <jarvinen@example.com>'


@pytest.mark.django_db(transaction=True)
def test_archive_message_encoded_word_alternate(client):
    """Test that encoded-word followed by non-whitespace,
    double quote or right paren, gets decoded properly
    """
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'encoded_word_2.mail')
    with open(path, 'rb') as f:
        data = f.read()
    status = archive_message(data, 'test', private=False)
    assert status == 0
    # ensure message in db
    assert Message.objects.all().count() == 1
    # ensure message in index
    url = '%s?q=encoded' % reverse('archive_search')
    response = client.get(url)
    assert len(response.context['results']) == 1
    message = Message.objects.first()
    print(message.frm)
    assert message.frm == 'J\xe4rvinen <jarvinen@example.com>'


@pytest.mark.django_db(transaction=True)
def test_archive_message_encoded_word_high_plane(client):
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'encoded_word_3.mail')
    with open(path, 'rb') as f:
        data = f.read()
    status = archive_message(data, 'test', private=False)
    assert status == 0
    # ensure message in db
    assert Message.objects.all().count() == 1
    # ensure message in index
    url = '%s?q=encoded' % reverse('archive_search')
    response = client.get(url)
    assert len(response.context['results']) == 1
    message = Message.objects.first()
    assert message.frm == '\U0001f513Joe <joe@example.com>'


@pytest.mark.django_db(transaction=True)
def test_archive_message_long_header_line(client):
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'long_header.mail')
    with open(path, 'rb') as f:
        data = f.read()
    status = archive_message(data, 'test', private=False)
    assert status == 0
    # ensure message in db
    assert Message.objects.all().count() == 1
    # ensure message on disk is not folded
    msg = Message.objects.first()
    print(msg.get_file_path())
    with open(msg.get_file_path()) as f:
        data = f.read()
    for line in data.splitlines():
        if line.startswith('Archived-At'):
            assert '=?' not in line 




def test_clean_spaces():
    s = 'this     is   a    string   with extra    spaces'
    assert clean_spaces(s) == 'this is a string with extra spaces'


def test_get_base_subject():
    data = [('[ANCP] =?iso-8859-1?q?R=FCckruf=3A_Welcome_to_the_=22ANCP=22_mail?=\n\t=?iso-8859-1?q?ing_list?=',
             'R\xfcckruf: Welcome to the "ANCP" mailing list'),
            ('Re: [IAB] Presentation at IAB Tech Chat (fwd)', 'Presentation at IAB Tech Chat'),
            ('Re: [82companions] [Bulk]  Afternoon North Coast tour', 'Afternoon North Coast tour'),
            ('''[cdni-footprint] Fwd: Re: [CDNi] Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"''', '''Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"'''),
            ('[dccp] [Fwd: Re: [Tsvwg] Fwd: WGLC for draft-ietf-dccp-quickstart-03.txt]', 'WGLC for draft-ietf-dccp-quickstart-03.txt'),
            ('[ANCP] Fw: note the boilerplate change', 'note the boilerplate change'),
            ('Re: [ANCP] RE: draft-ieft-ancp-framework-00.txt', 'draft-ieft-ancp-framework-00.txt')]

    message = email.message_from_string('From: rcross@amsl.com')
    mw = MessageWrapper(message, 'test')
    for item in data:
        normal = mw.normalize(item[0])
        base = get_base_subject(normal)
        assert base == item[1]


def test_get_envelope_date():
    data = [('From iesg-bounces@ietf.org Fri Dec 01 02:58:00 2006',
            datetime.datetime(2006, 12, 1, 2, 58)),                          # normal
            ('From denis.pinkas at bull.net  Fri Feb  1 03:12:00 2008',
            datetime.datetime(2008, 2, 1, 3, 12)),                           # obfiscated
            ('From fluffy@cisco.com Thu, 15 Jul 2004 17:15:16 -0700 (PDT)',
            datetime.datetime(2004, 7, 15, 17, 15, 16, tzinfo=tzoffset(None, -25200))),   # double tzinfo
            ('From Kim.Fullbrook@O2.COM Tue, 01 Feb 2005 06:01:13 -0500',
            datetime.datetime(2005, 2, 1, 6, 1, 13, tzinfo=tzoffset(None, -18000))),      # numeric tzinfo
            ('From eburger@brooktrout.com Thu, 3 Feb 2005 19:55:03 GMT',
            datetime.datetime(2005, 2, 3, 19, 55, 3, tzinfo=tzoffset(None, 0))),          # char tzinfo
            ('From scott.mcglashan@hp.com Wed, 6 Jul 2005 12:24:15 +0100 (BST)',
            datetime.datetime(2005, 7, 6, 12, 24, 15, tzinfo=tzoffset(None, 3600))),      # odd tzinfo
            ('From scoya  Fri Sep  1 02:28:00 2000',
            datetime.datetime(2000, 9, 1, 2, 28))]                           # simple from
    for item in data:
        message = email.message_from_string(item[0])
        assert get_envelope_date(message) == item[1]


def test_get_from():
    data = '''From rcross@amsl.com Fri Feb 21 11:09:00 2014
From: rcross@amsl.com
To: rcross@amsl.com
Subject: Test

Hello.
'''
    # test email.message.Message
    message = email.message_from_string(data)
    assert get_from(message) == 'From rcross@amsl.com Fri Feb 21 11:09:00 2014'

    # test mailbox.mboxMessage
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mbox.1')
    mb = mailbox.mbox(path)
    assert get_from(mb[0]) == 'internet-drafts@ietf.org  Wed Aug 21 16:20:36 2013'


def test_get_header_date():
    data = [('Date: Wed, 08 Apr 92 13:31:28 -0400',
            datetime.datetime(1992, 4, 8, 17, 31, 28)),      # 2-digit year, numeric tz
            ('Date: Thu, 28 May 92 9:18:58 PDT',
            datetime.datetime(1992, 5, 28, 16, 18, 58)),     # 2-digit year, char tz
            ('Date: Thursday, 28 May 1992 12:06:31 EDT',
            datetime.datetime(1992, 5, 28, 16, 6, 31)),     # full day name, char tz
            ('Date: Fri, 29 May 1992 18:02:45 -0400 (EDT)',
            datetime.datetime(1992, 5, 29, 22, 2, 45)),     # numeric & char tz
            ('Date: 27 Jan 2002 21:46:45 +0000',
            datetime.datetime(2002, 1, 27, 21, 46, 45)),     # no day of week
            ('Sent: Thu, 28 May 92 9:18:58 PDT',
            datetime.datetime(1992, 5, 28, 16, 18, 58))]     # Sent header
    for item in data:
        message = email.message_from_string(item[0])
        date = get_header_date(message)
        # convert to naive if we get a timezone aware object
        date = date.astimezone(pytz.utc).replace(tzinfo=None)
        assert date == item[1]


@pytest.mark.skip(reason='2019-03-02: only supporting standard mbox files')
def test_get_mb():
    files = glob.glob(os.path.join(settings.BASE_DIR, 'tests', 'data', 'mailbox_*'))
    for file in files:
        mb = get_mb(file)
        assert len(mb) > 0


def test_get_received_date():
    data = '''Received: from mail.ietf.org ([64.170.98.30]) by localhost \
(ietfa.amsl.com [127.0.0.1]) (amavisd-new, port 10024) with ESMTP id oE4MnXBb8IJ9 \
for <ancp@ietfa.amsl.com>; Tue, 29 Jan 2013 00:08:57 -0800 (PST)'''
    message = email.message_from_string(data)
    date = get_received_date(message)
    # convert to naive if we get a timezone aware object
    date = date.astimezone(pytz.utc).replace(tzinfo=None)
    assert date == datetime.datetime(2013, 1, 29, 8, 8, 57)


def test_is_aware():
    assert is_aware(datetime.datetime(2013, 1, 1)) is False
    assert is_aware(datetime.datetime(2013, 1, 1, 12, 0, 0, 0, pytz.UTC)) is True


def test_parsedate_to_datetime():
    date = 'Tue Jan  1 2014 12:30:00 PST'
    result = parsedate_to_datetime(date)
    assert isinstance(result, datetime.datetime)
    # TODO: assert we have the correct timezone


def test_subject_is_reply():
    assert subject_is_reply('This is a test') is False
    assert subject_is_reply('Re: This is a test') is True
    assert subject_is_reply('RE: This is a test') is True
    assert subject_is_reply('Re: [list] This is a test') is True
    assert subject_is_reply('Fwd: This is a test') is True
    assert subject_is_reply('[Fwd: This is a test]') is True
    assert subject_is_reply('This is a test (fwd)') is True
    assert subject_is_reply('[list] Fwd: Re: This is a test') is True
    assert subject_is_reply('[public] [Fwd: Re: [list] Fwd: This is a test]') is True

# def test_save_failed_msg

# def test_BetterMbox

# def test_Loader()

# --------------------------------------------------
# MessageWrapper
# --------------------------------------------------


def test_MessageWrapper_get_addresses():
    data = [('ancp@ietf.org',                               # simple
            'ancp@ietf.org'),
            ('Tom Taylor <tom.taylor.stds@gmail.com>',      # compound
            'Tom Taylor tom.taylor.stds@gmail.com'),
            ('Tom Taylor <tom.taylor.stds@gmail.com>, "ancp@ietf.org" <ancp@ietf.org>',
            'Tom Taylor tom.taylor.stds@gmail.com ancp@ietf.org ancp@ietf.org')]
    for item in data:
        assert MessageWrapper.get_addresses(item[0]) == item[1]


def test_MessageWrapper_get_cc():
    data = '''From: joe@acme.com
To: larry@acme.com
Cc: ancp@ietf.org
Subject: Hi
Date: Mon, 24 Feb 2014 08:04:41 -0800

This is the message.
'''
    msg = email.message_from_string(data)
    mw = MessageWrapper(msg, 'ancp')
    assert mw.get_to() == 'larry@acme.com'


@pytest.mark.django_db(transaction=True)
def test_MessageWrapper_get_thread():
    '''The same message can get sent to multiple lists.  Ensure
    get_thread finds the thread from the correct list
    '''
    list1 = EmailListFactory.create(name='list1')
    list2 = EmailListFactory.create(name='list2')
    thread1 = ThreadFactory.create()
    thread2 = ThreadFactory.create()
    MessageFactory.create(
        email_list=list1,
        msgid='001@example.com',
        thread=thread1,
        date=datetime.datetime(2016, 1, 1))
    MessageFactory.create(
        email_list=list2,
        msgid='001@example.com',
        thread=thread2,
        date=datetime.datetime(2016, 1, 1))
    data = '''From: joe@example.com
To: larry@example.com
Cc: list1@example.com
Subject: Re: New document
References: <001@example.com>
Message-Id: <002@example.com>
Date: Mon, 24 Feb 2016 08:04:41 -0800

This is the message.
'''
    msg = email.message_from_string(data)
    mw = MessageWrapper(msg, 'list1')
    assert mw.archive_message.thread == thread1


@pytest.mark.django_db(transaction=True)
def test_MessageWrapper_get_thread_subject():
    '''Test subject based threading'''
    elist = EmailListFactory.create(name='public')
    thread = ThreadFactory.create()
    MessageFactory.create(
        email_list=elist,
        msgid='001@example.com',
        subject='[public] New Members',
        base_subject='New Members',
        thread=thread,
        date=datetime.datetime(2016, 1, 1))
    data = '''From: joe@example.com
To: larry@example.com
Subject: Re: [public] New Members
Message-Id: <002@example.com>
Date: Mon, 24 Feb 2016 08:04:41 -0800

This is the message.
'''
    msg = email.message_from_string(data)
    mw = MessageWrapper(msg, 'public')
    assert mw.archive_message.thread == thread


@pytest.mark.django_db(transaction=True)
def test_MessageWrapper_get_thread_from_header():
    elist = EmailListFactory()
    message = MessageFactory.create(email_list=elist)
    data = '''From: joe@example.com
To: larry@example.com
Subject: Hello
References: <{msgid}>
Date: Mon, 24 Feb 2014 08:04:41 -0800

This is the message.
'''.format(msgid=message.msgid)
    msg = email.message_from_string(data)
    mw = MessageWrapper(msg, 'public')
    mw.process()
    assert mw.get_thread_from_header(mw.references) == message.thread


def test_MessageWrapper_get_to():
    data = '''From: joe@acme.com
To: larry@acme.com
Cc: ancp@ietf.org
Subject: Hi
Date: Mon, 24 Feb 2014 08:04:41 -0800

This is the message.
'''
    msg = email.message_from_string(data)
    mw = MessageWrapper(msg, 'ancp')
    assert mw.get_cc() == 'ancp@ietf.org'


@pytest.mark.django_db(transaction=True)
def test_MessageWrapper_process_attachments():
    msg = message_from_file('mail_multipart.1')
    mw = MessageWrapper(msg, 'public')
    mw.process()
    mw.archive_message.save()
    mw.process_attachments()
    assert mw.archive_message.attachment_set.count() == 1


@pytest.mark.django_db(transaction=True)
def test_MessageWrapper_process_attachments_non_ascii_filename():
    msg = message_from_file('mail_multipart_bad.2')
    mw = MessageWrapper(msg, 'public')
    mw.process()
    mw.archive_message.save()
    mw.process_attachments()
    # 2TO3: Python 2 get_filename() returns string (binary)
    # which gets discarded if non-ascii
    if sys.version_info > (3,0):
        assert mw.archive_message.attachment_set.count() == 1
    else:
        assert mw.archive_message.attachment_set.count() == 0
 


@pytest.mark.django_db(transaction=True)
def test_MessageWrapper_process_attachments_rfc2231_filename():
    msg = message_from_file('mail_multipart.2')
    mw = MessageWrapper(msg, 'public')
    mw.process()
    mw.archive_message.save()
    mw.process_attachments()
    assert mw.archive_message.attachment_set.count() == 1
    attachment = mw.archive_message.attachment_set.first()
    assert attachment.name == u'satellite-\u6d77\u6dc0\u533a\u5317\u6d3c\u8def4\u53f7.png'


def test_lookup_extension():
    assert lookup_extension('text/plain') == 'txt'
    assert lookup_extension('text/unknown_stuff') == 'txt'
    assert lookup_extension('text/x-csrc') == 'c'
    assert lookup_extension('image/jpeg') == 'jpeg'
    assert lookup_extension('text/html') == 'html'
    assert lookup_extension('hologram/3d') == 'bin'     # default for unknown


# test various exceptions raised
# test that older message added causes update to all tdates in index
