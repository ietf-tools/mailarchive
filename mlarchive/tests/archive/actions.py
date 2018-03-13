import os
import pytest

from factories import EmailListFactory, ThreadFactory, MessageFactory
from mlarchive.archive.actions import remove_selected, not_spam
from mlarchive.archive.models import Message
from mlarchive.utils.test_utils import get_request


@pytest.mark.django_db(transaction=True)
def test_remove_selected(admin_user):
    elist = EmailListFactory.create(name='public')
    thread = ThreadFactory.create()
    msg = MessageFactory.create(email_list=elist, thread=thread)

    # create message file
    path = msg.get_file_path()
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, 'w') as f:
        f.write('test.')

    # ensure message file doesn't already exist in removed directory
    target = os.path.join(msg.get_removed_dir(), msg.hashcode)
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
