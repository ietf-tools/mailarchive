import pytest
from mock import Mock
from mlarchive.utils.decorators import check_list_access

'''
def test_check_list_access_no_list():
    func = Mock(name='test')
    decorated_func = check_list_access(func)
    #request = prepare_request_without_user()
    response = decorated_func(request)
    assert not func.called
    # assert response is redirect


def test_check_list_access_no_access():
    func = Mock()
    decorated_func = check_list_access(func)
    #request = prepare_request_with_non_authenticated_user()
    response = decorated_func(request)
    assert not func.called
    # assert response is redirect


def test_check_list_access_ok():
    func = Mock(return_value='my response')
    decorated_func = check_list_access(func)
    #request = prepare_request_with_ok_user()
    response = decorated_func(request)
    func.assert_called_with(request)
    assert_equal(response, 'my response')
'''
