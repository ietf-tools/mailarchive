import pytest
import json
from mock import Mock


from django.http import HttpResponse
from django.test import RequestFactory
from mlarchive.utils.decorators import check_list_access, require_api_key
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


def get_error_message(response):
    content = response.content.decode('utf-8')
    data_as_dict = json.loads(content)
    return data_as_dict['error']


def test_require_api_key(settings):
    settings.API_KEYS = {'abcdefg': '/api/v1/message/'}
    rf = RequestFactory()
    func = Mock()
    rsp = HttpResponse()
    func.side_effect = [rsp, rsp, rsp, rsp, rsp, rsp]
    decorated_func = require_api_key(func)
    url = '/api/v1/message/'
    # no api key
    arequest = get_request()
    response = decorated_func(arequest)
    print(response, response.content)
    assert response.status_code == 400
    assert get_error_message(response) == 'Missing apikey'
    # bad api key
    brequest = get_request(url + '?apikey=bogus')
    response = decorated_func(brequest)
    print(response, response.content)
    assert response.status_code == 403
    assert get_error_message(response) == 'Invalid apikey'
    # api key in get
    crequest = get_request(url + '?apikey=abcdefg')
    response = decorated_func(crequest)
    print(response, response.content)
    assert response.status_code == 200
    # api key post form
    drequest = rf.post(url, data={'apikey': 'abcdefg'})
    response = decorated_func(drequest)
    print(response, response.content)
    assert response.status_code == 200
    # api key post header
    erequest = rf.post(url, headers={'X-API-Key': 'abcdefg'})
    response = decorated_func(erequest)
    print(response, response.content)
    assert response.status_code == 200
    # api key post header, endpoint mismatch
    frequest = rf.post('/api/v1/stats/', headers={'X-API-Key': 'abcdefg'})
    response = decorated_func(frequest)
    print(response, response.content)
    assert response.status_code == 400
    assert get_error_message(response) == 'Apikey endpoint mismatch'
    # assert func only called when apikey provided
    assert func.call_count == 3
    func.assert_any_call(crequest)
    func.assert_any_call(drequest)
    func.assert_any_call(erequest)
