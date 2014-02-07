import pytest
import sys

from django.core.urlresolvers import reverse
from factories import *
from mlarchive.archive.generator import *
from mlarchive.archive.management.commands._classes import archive_message
from mlarchive.archive.models import *
from pyquery import PyQuery

@pytest.mark.django_db(transaction=True)
def test_generator_as_text(client):
    data = '''From: Ryan Cross <rcross@amsl.com>
To: Ryan Cross <rcross@amsl.com>
Date: Thu, 7 Nov 2013 17:54:55 +0000
Message-ID: <0000000002@amsl.com>
Content-Type: text/plain; charset="us-ascii"
Subject: This is a test

Hello,

This is a test email.  database
'''
    status = archive_message(data,'test',private=False)
    assert status == 0
    msg = Message.objects.first()
    g = Generator(msg)
    text = g.as_text()

#@pytest.mark.django_db(transaction=True)
#def test_generator_as_html(client):

def test_generator_clean_headers():
    data = (('Date','Thu, 7 Nov 2013 17:54:55 +0000'),
            ('From','Ryan Cross <rcross@amsl.com>'),
            ('Subject','Hello Bj\xf6rn'),
            ('To','text'))
    output = Generator._clean_headers(data)
    assert output[2][1] == u'Hello Bj\xf6rn'
