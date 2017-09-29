import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from factories import *
from pprint import pprint
from pyquery import PyQuery
from StringIO import StringIO
from mlarchive.archive.models import Message, EmailList

import os
import shutil


@pytest.mark.django_db(transaction=True)
def test_ajax_get_msg(client):
    publist = EmailListFactory.create(name='public')
    prilist = EmailListFactory.create(name='private',private=True)
    user = UserFactory.create(is_superuser=True)
    prilist.members.add(user)
    thread = ThreadFactory.create()
    msg = MessageFactory.create(email_list=publist,thread=thread,hashcode='00001')
    primsg = MessageFactory.create(email_list=prilist,thread=thread,hashcode='00002')
    path = os.path.join(settings.BASE_DIR,'tests','data','mail.1')
    for m in (msg,primsg):
        if not os.path.exists(os.path.dirname(m.get_file_path())):
            os.makedirs(os.path.dirname(m.get_file_path()))
        shutil.copyfile(path, m.get_file_path())

    url = '%s/?id=%s' % (reverse('ajax_get_msg'), msg.pk)
    response = client.get(url)
    assert response.status_code == 200
    assert response.content.find('This is a test') != -1

    # test unauthorized access to restricted Message
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), primsg.pk)
    response = client.get(url)
    assert response.status_code == 403

    # test authorized access to restricted Message
    assert client.login(username='admin',password='admin')
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), primsg.pk)
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_ajax_get_msg_thread_links(client, thread_messages):
    msg = Message.objects.get(msgid='00002@example.com')
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), msg.pk)
    response = client.get(url)
    assert response.status_code == 200
    
    q = PyQuery(response.content)
    assert q('#message-thread').length == 1
    assert len(response.context['references']) == 1
    assert q('.thread-ref-link').length == 1
    assert len(response.context['replies']) == 1
    assert q('.thread-reply-link').length == 1
    
@pytest.mark.django_db(transaction=True)
def test_ajax_get_messages(client,messages):
    # run initial query to setup cache
    url = '%s/?email_list=pubone&email_list=pubtwo' % reverse('archive_search')
    response = client.get(url)
    assert response.status_code == 200
    # for x in response.context['results']:
    #     print type(x)
    assert len(response.context['results']) == 6
    q = PyQuery(response.content)
    id = q('.msg-list').attr('data-queryid')

    print id,
    print cache.get(id)

    # test successful get_messages call
    url = '%s/?qid=%s&lastitem=2' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('.xtr')) > 1

    # test end of results
    url = '%s/?qid=%s&lastitem=40' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 204

    # test expired cache
    cache.delete(id)
    url = '%s/?qid=%s&lastitem=20' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 404

@pytest.mark.django_db(transaction=True)
def test_ajax_admin_action(client):
    user = UserFactory.create(is_superuser=True)
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist)
    client.login(username='admin',password='admin')
    url = reverse('ajax_admin_action')
    data = {'action':'remove_selected', 'ids':'%s' % msg.pk}
    response = client.post(url, data)
    assert response.status_code == 200
    assert Message.objects.count() == 0

