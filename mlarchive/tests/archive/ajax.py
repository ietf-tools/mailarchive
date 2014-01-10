import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from factories import *
from pprint import pprint
from pyquery import PyQuery

import os
import shutil

@pytest.mark.django_db(transaction=True)
def test_ajax_get_list(client):
    url = '%s?term=p' % reverse('ajax_get_list')
    response = client.get(url)
    assert response.content == '{"success": false, "error": "No results"}'
    publist = EmailListFactory.create(name='public')
    prilist = EmailListFactory.create(name='private',private=True)
    alist = EmailListFactory.create(name='ancp')

    # not logged in
    response = client.get(url)
    assert response.content == '[{"id": 1, "label": "public"}]'

    # logged in
    user = UserFactory.create(username='test-chair')
    prilist.members.add(user)
    assert client.login(username='test-chair',password='ietf-test')
    response = client.get(url)
    assert response.content  == '[{"id": 1, "label": "public"}, {"id": 2, "label": "private"}]'

@pytest.mark.django_db(transaction=True)
def test_ajax_get_msg(client):
    publist = EmailListFactory.create(name='public')
    prilist = EmailListFactory.create(name='private',private=True)
    user = UserFactory.create(username='test-chair')
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
    assert client.login(username='test-chair',password='ietf-test')
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), primsg.pk)
    response = client.get(url)
    print response
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_ajax_get_messages(client):
    '''
    This test expects data in the xapian index.  However, since the database is empty search
    result sets will contain empty items
    '''
    pass
    '''
    this may require testing against a live system
        
    url = '%s/?q=database' % reverse('archive_search')
    response = client.get(url)
    count = response.context['page'].paginator.count
    pprint(response.context['page'].object_list)
    assert count > 20
    q = PyQuery(response.content)
    id = q('#msg-list').attr('data-queryid')

    url = '%s/?queryid=%s&lastitem=20' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 200

    # expire item and try again
    cache.delete(id)
    response = client.get(url)
    assert response.status_code == 404

    # test end of items
    url = '%s/?queryid=%s&lastitem=%s' % (reverse('ajax_messages'), id, count + 1)
    response = client.get(url)
    print response.content
    print response.status_code
    print url
    assert response.status_code == 204
    '''