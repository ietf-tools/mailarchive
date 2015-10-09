import pytest

import os
from django.conf import settings
from mlarchive.archive.models import Message, EmailList

@pytest.mark.django_db(transaction=True)
def test_message_get_from_line(client,messages):
    '''Test that non-ascii text doesn't cause errors'''
    msg = Message.objects.first()
    msg.frm = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.from_line = ''
    msg.save()
    assert msg.get_from_line()

    msg.from_line = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.save()
    assert msg.get_from_line()

@pytest.mark.django_db(transaction=True)
def test_notify_new_list(client,tmpdir,settings):
    settings.EXPORT_DIR = str(tmpdir)
    EmailList.objects.create(name='dummy')
    path = os.path.join(settings.EXPORT_DIR,'email_lists.xml')
    assert os.path.exists(path)
    with open(path) as file:
        assert 'dummy' in file.read()