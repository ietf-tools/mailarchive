from mlarchive.archive.management.commands._classes import *
from factories import *
from pprint import pprint

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
def test_archive_message(client):
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
    assert Message.objects.all().count() == 1
    
    url = '%s/?q=database' % reverse('archive_search')
    response = client.get(url)
    count = response.context['page'].paginator.count
    pprint(response.context['page'].object_list)
    assert count > 20


@pytest.mark.django_db(transaction=True)
def test_archive_message_fail(client):
    data = '''Hello,

This is a test email.  With no headers
'''
    publist = EmailListFactory.create(name='public')
    status = archive_message(data,'public',private=False)
    assert status == 1
    assert Message.objects.all().count() == 0
    filename = datetime.datetime.today().strftime('%Y-%m-%d') + '.0000'
    print publist.get_failed_dir()
    print filename
    assert os.path.exists(os.path.join(publist.get_failed_dir(),filename))

#def test_save_failed_msg

#def test_get_envelope_date():
    # from most common to least
    # From iesg-bounces@ietf.org Fri Dec 01 02:58:22 2006
    # From denis.pinkas at bull.net  Fri Feb  1 03:12:37 2008
    # From fluffy@cisco.com Thu, 15 Jul 2004 17:15:16 -0700 (PDT)
    # From Kim.Fullbrook@O2.COM Tue, 01 Feb 2005 06:01:13 -0500
    # From eburger@brooktrout.com Thu, 3 Feb 2005 19:55:03 GMT
    # From scott.mcglashan@hp.com Wed, 6 Jul 2005 12:24:15 +0100 (BST)
    
def test_get_mime_extension():
    data = [('image/jpeg','jpg'),('text/html','html'),('hologram/3d','bin')]
    for item in data:
        ext, desc = get_mime_extension(item[0])
        assert ext == item[1]
        