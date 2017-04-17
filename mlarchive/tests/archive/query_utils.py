
from haystack.query import SearchQuerySet
from django.core.cache import cache
from django.http import QueryDict
from django.test import RequestFactory

from mlarchive.archive.query_utils import *

def test_clean_queryid():
    # good queryid
    good_queryid = 'df6d7ccfedface723ffb184a6f52bab3'
    assert clean_queryid(good_queryid) == good_queryid
    # bad queryid
    bad_queryid = "df6d7ccfedface723ffb184a6f52bab3'+order+by+1+--+;"
    assert clean_queryid(bad_queryid) == None

def test_get_cached_query():
    sqs = SearchQuerySet()
    queryid = generate_queryid()
    cache.set(queryid,sqs)
    request_factory = RequestFactory()
    # using dummy url, only the qid parameter matters here
    request = request_factory.get('/arch',{'qid':queryid})
    assert get_cached_query(request)

def test_generate_queryid():
    queryid = generate_queryid()
    assert clean_queryid(queryid)

def test_get_filter_params():
    assert get_filter_params(QueryDict('f_list=pub')) == ['f_list']
    assert get_filter_params(QueryDict('f_from=joe')) == ['f_from']
    assert get_filter_params(QueryDict('f_list=pub&f_from=joe')) == ['f_list','f_from']
    assert get_filter_params(QueryDict('f_list=')) == []
    