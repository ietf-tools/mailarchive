import pytest

from mock import patch

from django.http import JsonResponse
from mlarchive.archive.actions import remove_selected, not_spam


@pytest.mark.django_db(transaction=True)
def test_temporary_directory(messages):
    assert 'pytest' in messages.first().get_file_path()


@patch('mlarchive.archive.tasks.remove_selected_task.delay')
@pytest.mark.django_db(transaction=True)
def test_remove_selected(mock_update, rf, admin_user, messages):
    '''Simple test of function. See tests/archive/utils.py for test
    of underlying functionality'''
    request = rf.post(
        '/arch/admin/',
        data={'action': 'remove_selected'},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    request.user = admin_user
    response = remove_selected(request, messages)
    assert isinstance(response, JsonResponse)
    assert response.status_code == 200
    mock_update.assert_called_with(user_id=admin_user.id)


@patch('mlarchive.archive.tasks.mark_not_spam_task.delay')
@pytest.mark.django_db(transaction=True)
def test_not_spam(mock, rf, admin_user, messages):
    '''Simple test of function. See tests/archive/utils.py for test
    of underlying functionality'''
    request = rf.post(
        '/arch/admin/',
        data={'action': 'not_spam'},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    request.user = admin_user
    response = not_spam(request, messages)
    assert isinstance(response, JsonResponse)
    assert response.status_code == 200
    assert mock.called is True
