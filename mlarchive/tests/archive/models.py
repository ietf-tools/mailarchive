import pytest

import os
from django.conf import settings
from mlarchive.archive.models import Message, EmailList

@pytest.mark.django_db(transaction=True)
def test_message_get_from_line(client,messages):
    msg = Message.objects.first()
    msg.frm = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.save()
    assert msg.get_from_line()
    
@pytest.mark.django_db(transaction=True)
def test_notify_new_list(client):
    EmailList.objects.create(name='dummy')
    path = os.path.join(settings.EXPORT_DIR,'email_list.xml')
    assert os.path.exists(path)
    with open(path) as file:
        assert 'dummy' in file.read()