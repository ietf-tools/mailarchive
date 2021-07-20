from __future__ import absolute_import, division, print_function, unicode_literals

import os
import pytest

from mock import patch
from factories import EmailListFactory, ThreadFactory, MessageFactory
from mlarchive.archive.actions import remove_selected, not_spam, get_mbox_updates
from mlarchive.archive.models import Message, EmailList
from mlarchive.utils.test_utils import get_request

@pytest.mark.django_db(transaction=True)
def test_temporary_directory(messages):
    assert 'pytest' in messages.first().get_file_path()


@pytest.mark.django_db(transaction=True)
def test_get_mbox_updates(messages):
    apple = EmailList.objects.get(name='apple')
    print(apple.message_set.count())
    result = get_mbox_updates(apple.message_set.all())
    assert result == [(1,2017,apple.pk)]

@patch('celery_haystack.tasks.update_mbox.delay')
@pytest.mark.django_db(transaction=True)
def test_remove_selected(mock_update, admin_user):
    mock_update.return_value = 1
    elist = EmailListFactory.create(name='public')
    thread = ThreadFactory.create()
    msg = MessageFactory.create(email_list=elist, thread=thread)

    # create message file
    path = msg.get_file_path()
    # print(path)
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, 'w') as f:
        f.write('test.')

    # ensure message file doesn't already exist in removed directory
    target = os.path.join(msg.get_removed_dir(), msg.hashcode)
    # print('target: {}'.format(target))
    if os.path.exists(target):
        os.remove(target)

    query = Message.objects.all()
    assert query.count() == 1
    request = get_request(user=admin_user)
    result = remove_selected(request, query)

    assert result.status_code == 302
    assert os.path.exists(target)
    assert not os.path.exists(path)
    assert Message.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_not_spam(admin_user):
    elist = EmailListFactory.create(name='public')
    thread = ThreadFactory.create()
    msg = MessageFactory.create(email_list=elist, thread=thread, spam_score=1)

    query = Message.objects.all()
    assert query.count() == 1
    request = get_request(user=admin_user)
    not_spam(request, query)

    msg = Message.objects.first()
    assert msg.spam_score == -1
