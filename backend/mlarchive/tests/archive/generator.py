import email
import os
import pytest

from django.conf import settings
from django.test.client import RequestFactory
from mlarchive.archive.generator import Generator
from mlarchive.archive.management.commands._classes import archive_message
from mlarchive.archive.models import Message
from mlarchive.utils.test_utils import message_from_file

from pyquery import PyQuery

# --------------------------------------------------
# Some data
# --------------------------------------------------

data = '''From: Ryan Cross <rcross@amsl.com>
To: Ryan Cross <rcross@amsl.com>
Date: Thu, 7 Nov 2013 17:54:55 +0000
Message-ID: <0000000002@amsl.com>
Content-Type: text/plain; charset="us-ascii"
Subject: This is a test

Hello,

This is a test email.  database
'''

# --------------------------------------------------
# Test Functions
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_generator_as_text(client):
    status = archive_message(data, 'test', private=False)
    assert status == 0
    msg = Message.objects.first()
    g = Generator(msg)
    text = g.as_text()
    assert text == u'Hello,\r\n\r\nThis is a test email.  database\r\n'


@pytest.mark.django_db(transaction=True)
def test_generator_as_html(client):
    status = archive_message(data, 'test', private=False)
    assert status == 0
    msg = Message.objects.first()
    g = Generator(msg)
    factory = RequestFactory()
    html = g.as_html(factory.get('/arch'))
    q = PyQuery(html)
    assert len(q('div#msg-body')) == 1


@pytest.mark.django_db(transaction=True)
def test_handle_text_html_text_only(client, messages):
    msg = message_from_file('mail_html.1')
    g = Generator(Message.objects.first())
    g.text_only = True
    output = g._handle_text_html(msg)
    assert output.strip() == u'linkname'


@pytest.mark.django_db(transaction=True)
def test_handle_text_html_secure(client, messages):
    # ensure that handle_text_html strips unwanted, dangerous tags (script, etc)
    msg = message_from_file('mail_html_unsafe.1')
    g = Generator(Message.objects.first())
    g.text_only = False
    output = g._handle_text_html(msg)
    assert output.lower().find('<script') == -1
    assert output.lower().find('<body') == -1
    assert output.lower().find('<form') == -1
    assert output.lower().find('<html') == -1
    assert output.lower().find('<head') == -1
    assert output.lower().find('<style') == -1

# @pytest.mark.django_db(transaction=True)
# def test_handle_text_plain(client,messages):


@pytest.mark.django_db(transaction=True)
def test_handle_text_enriched(client):
    msg = message_from_file('mail_text_enriched.1')
    status = archive_message(msg.as_string(), 'test')
    assert status == 0
    generator = Generator(Message.objects.first())
    output = generator.as_text()
    assert 'This is a test email' in output


'''
@pytest.mark.django_db(transaction=True)
def test_handle_message_delivery_status(client):
    msg = message_from_file('mail_delivery_status.1')
    status = archive_message(msg.as_string(), 'test', private=False)
    assert status == 0
    generator = Generator(Message.objects.first())
    generator.text_only = False
    part = list(msg.walk())[2]
    assert part.get_content_type() == 'message/delivery-status'
    output = generator._dispatch(part)
    assert 'Action: failed' in output
'''


@pytest.mark.django_db(transaction=True)
def test_handle_message_external_body_type_a(client):
    msg = message_from_file('mail_external_body.1')
    status = archive_message(msg.as_string(), 'test', private=False)
    assert status == 0
    generator = Generator(Message.objects.first())
    generator.text_only = False
    part = list(msg.walk())[2]
    assert part.get_content_type() == 'message/external-body'
    output = generator._dispatch(part)
    q = PyQuery(output)
    href = q('a').attr('href')
    assert href == 'ftp://ftp.ietf.org/internet-drafts/draft-ietf-ancp-framework-06.txt'


@pytest.mark.django_db(transaction=True)
def test_handle_message_external_body_type_a_invalid(client):
    msg = message_from_file('mail_external_body_invalid.1')
    status = archive_message(msg.as_string(), 'test', private=False)
    assert status == 0
    generator = Generator(Message.objects.first())
    generator.text_only = False
    part = list(msg.walk())[2]
    assert part.get_content_type() == 'message/external-body'
    assert generator._dispatch(part) is None


@pytest.mark.django_db(transaction=True)
def test_handle_message_external_body_type_b(client):
    msg = message_from_file('mail_external_body.2')
    status = archive_message(msg.as_string(), 'test', private=False)
    assert status == 0
    generator = Generator(Message.objects.first())
    generator.text_only = False
    part = list(msg.walk())[2]
    assert part.get_content_type() == 'message/external-body'
    output = generator._dispatch(part)
    assert output.find('[InternetShortcut]') != -1


def test_generator_clean_headers():
    data = (('Date', 'Thu, 7 Nov 2013 17:54:55 +0000'),
            ('From', 'Ryan Cross <rcross@amsl.com>'),
            ('Subject', 'Hello Bj\xf6rn'),
            ('To', 'text'))
    output = Generator._clean_headers(data)
    assert output[2][1] == u'Hello Bj\xf6rn'


@pytest.mark.django_db(transaction=True)
def test_generator_multipart_malformed(client):
    msg = message_from_file('mail_multipart_bad.1')
    status = archive_message(data, 'test', private=False)
    assert status == 0
    msg = Message.objects.first()
    g = Generator(msg)
    text = g.as_text()
    assert isinstance(text, basestring)
