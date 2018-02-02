import pytest

from django.urls import reverse
from pyquery import PyQuery

from mlarchive.archive.models import Message, Thread
from mlarchive.archive.thread import compute_thread


@pytest.mark.django_db(transaction=True)
def test_thread_view(client, thread_messages):
    '''Check order of messages in thread view'''
    info = compute_thread(Thread.objects.first())
    print info
    for m in Message.objects.all().order_by('thread_order'):
        print m.pk, m.thread_order
    url = reverse('archive_search') + '?email_list=acme&gbt=1'
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('.msg-list .xtr')) == 4
    ids = q('.msg-list .xtr .xtd.id-col').items()
    results = [Message.objects.get(pk=i.text()).msgid for i in ids]
    expected = [u'00001@example.com', u'00002@example.com', u'00004@example.com', u'00003@example.com']
    assert results == expected
