from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from django.core.cache import cache
from django.conf import settings
from django.http import QueryDict
from django.test import RequestFactory
from django.urls import reverse
from factories import EmailListFactory

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search

from mlarchive.archive.query_utils import (clean_queryid, generate_queryid, get_cached_query,
    get_filter_params, get_browse_equivalent, parse_query, map_sort_option, get_order_fields,
    DB_THREAD_SORT_FIELDS, IDX_THREAD_SORT_FIELDS, DEFAULT_SORT, get_count,
    CustomPaginator)
from mlarchive.utils.test_utils import get_request


def test_clean_queryid():
    # good queryid
    good_queryid = 'df6d7ccfedface723ffb184a6f52bab3'
    assert clean_queryid(good_queryid) == good_queryid
    # bad queryid
    bad_queryid = "df6d7ccfedface723ffb184a6f52bab3'+order+by+1+--+;"
    assert clean_queryid(bad_queryid) is None


def test_get_cached_query():
    client = Elasticsearch()
    search = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    queryid = generate_queryid()
    cache.set(queryid, search.to_dict())
    request_factory = RequestFactory()
    # using dummy url, only the qid parameter matters here
    request = request_factory.get('/arch', {'qid': queryid})
    assert get_cached_query(request)


def test_generate_queryid():
    queryid = generate_queryid()
    assert clean_queryid(queryid)


def test_get_filter_params():
    assert get_filter_params(QueryDict('f_list=pub')) == ['f_list']
    assert get_filter_params(QueryDict('f_from=joe')) == ['f_from']
    assert 'f_list' in get_filter_params(QueryDict('f_list=pub&f_from=joe'))
    assert 'f_from' in get_filter_params(QueryDict('f_list=pub&f_from=joe'))
    assert get_filter_params(QueryDict('f_list=')) == []


def test_map_sort_option():
    assert map_sort_option('invalid') == ''
    assert map_sort_option('frm') == 'frm_name'
    assert map_sort_option('-frm') == '-frm_name'


@pytest.mark.django_db(transaction=True)
def test_get_browse_equivalent():
    EmailListFactory.create(name='pubone')
    url = '%s?%s' % (reverse('archive_search'), 'q=pubone')
    request = get_request(url=url)
    assert get_browse_equivalent(request) == 'pubone'
    url = '%s?%s' % (reverse('archive_search'), 'q=dummy')
    request = get_request(url=url)
    assert get_browse_equivalent(request) is None
    url = '%s?%s' % (reverse('archive_search'), 'q=pubone&qdr=w')
    request = get_request(url=url)
    assert get_browse_equivalent(request) is None
    url = '%s?%s' % (reverse('archive_search'), 'email_list=pubone')
    request = get_request(url=url)
    assert get_browse_equivalent(request) == 'pubone'


def test_parse_query():
    factory = RequestFactory()
    # simple query
    request = factory.get('/arch/search/?q=dummy')
    assert parse_query(request) == 'dummy'
    # advanced query
    request = factory.get(
        '/arch/search/?as=1&nojs-query-0-field=text&nojs-query-0-qualifier=contains&nojs-query-0-value=dummy')
    assert parse_query(request) == 'text:(dummy)'
    # advanced query with nots
    request = factory.get(
        '/arch/search/?as=1&nojs-query-0-field=text&nojs-query-0-qualifier=contains&nojs-query-0-value=dummy&nojs-not-0-field=from&nojs-not-0-qualifier=contains&nojs-not-0-value=jones')  # noqa
    assert parse_query(request) == 'text:(dummy) -from:(jones)'


def test_get_order_fields():
    assert get_order_fields({'q': 'term'}) == [DEFAULT_SORT]
    assert get_order_fields({'q': 'term', 'so': ''}) == [DEFAULT_SORT]                         # empty param, "?q=term&so="
    assert get_order_fields({'q': 'term', 'so': 'date'}) == ['date']
    assert get_order_fields({'q': 'term', 'gbt': '1'}) == IDX_THREAD_SORT_FIELDS
    assert get_order_fields({'q': 'term', 'gbt': '1'}, use_db=True) == DB_THREAD_SORT_FIELDS
    assert get_order_fields({'q': 'term', 'gbt': '1', 'so': 'date'}) == IDX_THREAD_SORT_FIELDS      # gbt takes precedence
    assert get_order_fields({'q': 'term', 'so': 'date', 'sso': 'subject'}) == ['date', 'base_subject']
    assert get_order_fields({'q': 'term', 'so': 'frm'}) == ['frm_name']                         # frm gets mapped


@pytest.mark.django_db(transaction=True)
def test_get_count(messages):
    client = Elasticsearch()
    base = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    # good query
    s = base.query('query_string', query='message', default_field='text')
    assert get_count(s) > 0
    # bad query
    s = base.query('query_string', query='-', default_field='text')
    assert get_count(s) == 0


@pytest.mark.django_db(transaction=True)
def test_CustomPaginator(messages):
    # make query with large result set
    client = Elasticsearch()
    base = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    s = base.query('match', email_list='pubthree')
    assert s.count() == 21
    # 
    paginator = CustomPaginator(s, 10)
    assert paginator.count == 21
    assert paginator.num_pages == 3
    page = paginator.page(1)
    assert page.number == 1
    assert page.has_previous() is False
    assert page.has_next() is True
    assert page.start_index() == 1
    assert hasattr(page, '__iter__')
    assert len(page) == 10
