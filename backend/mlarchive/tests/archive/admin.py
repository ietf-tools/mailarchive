import pytest
from mock import patch

from django.urls import reverse

from factories import EmailListFactory
from mlarchive.archive.models import TaskLock
from mlarchive.archive.utils import move_list_blobs_lock_name


@pytest.mark.django_db(transaction=True)
def test_move_message_blobs_action(admin_client):
    """The action queues one move per selected list, with the visibility the admin saw."""
    public = EmailListFactory.create(name='public', private=False)
    private = EmailListFactory.create(name='private', private=True)
    url = reverse('admin:archive_emaillist_changelist')

    with patch('mlarchive.archive.admin.move_list_blobs_task.delay') as delay:
        response = admin_client.post(url, {
            'action': 'move_message_blobs',
            '_selected_action': [public.pk, private.pk]}, follow=True)

    assert response.status_code == 200
    queued = {(call.kwargs['list_id'], call.kwargs['private']) for call in delay.call_args_list}
    assert delay.call_count == 2
    assert queued == {(public.pk, False), (private.pk, True)}
    assert 'Queued a blob move for 2 list(s)' in response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_move_message_blobs_action_skips_locked_list(admin_client):
    """A list whose move is already running is not queued again, and the admin is warned."""
    locked = EmailListFactory.create(name='locked', private=True)
    free = EmailListFactory.create(name='free', private=False)
    TaskLock.objects.create(name=move_list_blobs_lock_name(locked.pk))
    url = reverse('admin:archive_emaillist_changelist')

    with patch('mlarchive.archive.admin.move_list_blobs_task.delay') as delay:
        response = admin_client.post(url, {
            'action': 'move_message_blobs',
            '_selected_action': [locked.pk, free.pk]}, follow=True)

    delay.assert_called_once_with(list_id=free.pk, private=False)
    content = response.content.decode()
    assert 'A blob move for locked has been running since' in content
    assert 'Queued a blob move for 1 list(s)' in content
