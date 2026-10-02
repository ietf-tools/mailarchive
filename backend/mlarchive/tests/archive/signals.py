import datetime
import os
import pytest
from datetime import timezone

from factories import EmailListFactory, ThreadFactory, MessageFactory

from mlarchive.archive.models import EmailList, Message, Thread


@pytest.mark.django_db(transaction=True)
def test_message_remove(client, thread_messages):
    message = Message.objects.first()
    path = message.get_file_path()
    removed_path = os.path.join(message.get_removed_dir(), message.hashcode)

    # ensure message file doesn't already exist in removed directory
    if os.path.exists(removed_path):
        os.remove(removed_path)

    assert os.path.exists(path)
    message.delete()
    assert not os.path.exists(path)
    assert os.path.exists(removed_path)


@pytest.mark.django_db(transaction=True)
def test_message_save(client):
    now = datetime.datetime.now(timezone.utc).replace(second=0, microsecond=0)
    public = EmailListFactory.create(name='public', private=False)
    thread = ThreadFactory.create()
    MessageFactory.create(
        email_list=public,
        date=now,
        thread=thread)
    thread = Thread.objects.get(pk=thread.pk)
    assert thread.date == now


@pytest.mark.django_db(transaction=True)
def test_notify_new_list(client, tmpdir, settings):
    settings.EXPORT_DIR = str(tmpdir)
    EmailList.objects.create(name='dummy')
    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    date_string = today_utc.strftime('%Y%m%d')
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.{}.xml'.format(date_string))
    assert os.path.exists(path)
    with open(path) as file:
        assert 'dummy' in file.read()
