import pytest
import json
from mock import Mock


from django.http import HttpResponse
from django.test import RequestFactory
from mlarchive.utils.decorators import (check_list_access, require_api_key,
    is_valid_token)
from mlarchive.utils.test_utils import get_request

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


def test_is_valid_token(settings):
    settings.API_KEYS = {'/api/v1/message/import/': 'valid_token'}
    assert is_valid_token('/api/v1/message/import/', 'valid_token') is True
    assert is_valid_token('/api/v1/message/import/', 'invvalid_token') is False
    assert is_valid_token('/api/v1/different/endpoint/', 'valid_token') is False


def test_require_api_key(settings):
    settings.API_KEYS = {'/api/v1/message/import/': 'abcdefg'}
    rf = RequestFactory()
    func = Mock()
    rsp = HttpResponse()
    func.side_effect = [rsp, rsp, rsp, rsp, rsp, rsp]
    decorated_func = require_api_key(func)
    url = '/api/v1/message/import/'
    # no api key
    arequest = rf.post(url, data={})
    response = decorated_func(arequest)
    assert response.status_code == 403
    # bad api key
    brequest = rf.post(url, headers={'X-API-Key': 'bogus'})
    response = decorated_func(brequest)
    assert response.status_code == 403
    # good api key
    crequest = rf.post(url, headers={'X-API-Key': 'abcdefg'})
    response = decorated_func(crequest)
    print(response, response.content)
    assert response.status_code == 200
    # api key post header, endpoint mismatch
    drequest = rf.post('/api/v1/stats/', headers={'X-API-Key': 'abcdefg'})
    response = decorated_func(drequest)
    print(response, response.content)
    assert response.status_code == 403
    # assert func only called when apikey provided
    assert func.call_count == 1
    func.assert_any_call(crequest)
