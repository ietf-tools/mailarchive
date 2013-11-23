from mlarchive.archive.management.commands._classes import *

import datetime
import email
import pytest

def test_get_base_subject():
    data = [('[ANCP] =?iso-8859-1?q?R=FCckruf=3A_Welcome_to_the_=22ANCP=22_mail?=\n\t=?iso-8859-1?q?ing_list?=',
             'R\xc3\xbcckruf: Welcome to the "ANCP" mailing list'),
            ('Re: [IAB] Presentation at IAB Tech Chat (fwd)','Presentation at IAB Tech Chat'),
            ('Re: [82companions] [Bulk]  Afternoon North Coast tour','Afternoon North Coast tour'),
            ('''[cdni-footprint] Fwd: Re: [CDNi] Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"''','''Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"'''),
            ('[dccp] [Fwd: Re: [Tsvwg] Fwd: WGLC for draft-ietf-dccp-quickstart-03.txt]','WGLC for draft-ietf-dccp-quickstart-03.txt'),
            ('[ANCP] Fw: note the boilerplate change','note the boilerplate change'),
            ('Re: [ANCP] RE: draft-ieft-ancp-framework-00.txt','draft-ieft-ancp-framework-00.txt')]

    message = email.message_from_string('From: rcross@amsl.com')
    mw = MessageWrapper(message, 'test')
    for item in data:
        normal = mw.normalize(item[0])
        base = get_base_subject(normal)
        assert base == item[1]

@pytest.mark.django_db(transaction=True)
def test_archive_message():
    data = '''From: Ryan Cross <rcross@amsl.com>
To: Ryan Cross <rcross@amsl.com>
Date: Thu, 7 Nov 2013 17:54:55 +0000
Message-ID: <0000000002@amsl.com>
Content-Type: text/plain; charset="us-ascii"
Subject: This is a test

Hello,

This is a test email.
'''
    status = archive_message(data,'test',private=False)
    assert status == 0
    assert Message.objects.all().count() == 1

@pytest.mark.django_db(transaction=True)
def test_archive_message_fail(client):
    data = '''Hello,

This is a test email.  With no headers
'''
    from django.conf import settings
    print settings.ARCHIVE_DIR
    status = archive_message(data,'test',private=False)
    assert status == 1
    assert Message.objects.all().count() == 0
    filename = datetime.datetime.today().strftime('%Y-%m-%d') + '.0000'
    assert os.path.exists(os.path.join('/tmp/archive/_failed/test/',filename))

#def test_save_failed_msg