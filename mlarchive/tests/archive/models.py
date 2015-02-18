import pytest

from mlarchive.archive.models import *

@pytest.mark.django_db(transaction=True)
def test_message_get_from_line(client,messages):
    msg = Message.objects.first()
    msg.frm = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.save()
    assert msg.get_from_line()
