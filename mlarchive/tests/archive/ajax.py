import pytest
from django.conf import settings
from django.core.urlresolvers import reverse
from factories import *

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
def test_get_msg(client):
    elist = EmailListFactory.create(name='public')
    thread = ThreadFactory.create()
    msg = MessageFactory.create(email_list=elist,thread=thread)
    path = os.path.join(settings.BASE_DIR,'tests','data','mail.1')
    shutil.copyfile(path, msg.get_file_path())

    url = '%s/?id=1' % reverse('ajax_get_msg')
    response = client.get(url)
    print response.content
    assert False

@pytest.mark.django_db(transaction=True)
def test_get_messages(client):
    pass