''' tests.archive.forms.py'''

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.http import HttpRequest, QueryDict
from django.test.client import RequestFactory
from factories import *
from haystack.query import SearchQuerySet
from mlarchive.archive.forms import *
from pprint import pprint
from pyquery import PyQuery


def test_get_base_query():
    qd = QueryDict('?q=database&f_list=saag&so=date')
    result = get_base_query(qd)
    assert isinstance(result, QueryDict)
    assert result.items() == [(u'?q', u'database')]
    result = get_base_query(qd,filters=True)
    assert isinstance(result, QueryDict)
    assert result.items() == [(u'f_list', u'saag'), (u'?q', u'database')]
    result = get_base_query(qd,string=True)
    assert isinstance(result, unicode)
    assert result == u'%3Fq=database'

@pytest.mark.django_db(transaction=True)
def test_get_cache_key():
    factory = RequestFactory()
    # test regular
    url = reverse('archive_search') + '?q=database'
    request=factory.get(url)
    request.user=AnonymousUser()
    key = get_cache_key(request)
    assert key
    # sort param should not change key
    url = reverse('archive_search') + '?q=database&so=date'
    request=factory.get(url)
    request.user=AnonymousUser()
    key2 = get_cache_key(request)
    assert key == key2
    # user should change key
    url = reverse('archive_search') + '?q=database'
    request=factory.get(url)
    request.user=UserFactory.build()
    key3 = get_cache_key(request)
    assert key != key3
    # test encoded URL
    url = reverse('archive_search') + '?q=database%E2%80%8F'
    request=factory.get(url)
    request.user=AnonymousUser()
    key4 = get_cache_key(request)
    assert key4
    
@pytest.mark.django_db(transaction=True)
def test_get_list_info():
    EmailListFactory.create(name='ancp')
    EmailListFactory.create(name='alto')
    assert get_list_info(1) == 'ancp'
    assert get_list_info('ancp') == 1

def test_get_query():
    factory = RequestFactory()
    # simple query
    request=factory.get('/arch/search/?q=dummy')
    assert get_query(request) == 'dummy'
    # advanced query 
    request=factory.get('/arch/search/?as=1&nojs-query-0-field=text&nojs-query-0-qualifier=contains&nojs-query-0-value=dummy')
    assert get_query(request) == 'text:(dummy)'
    # advanced query with nots
    request=factory.get('/arch/search/?as=1&nojs-query-0-field=text&nojs-query-0-qualifier=contains&nojs-query-0-value=dummy&nojs-not-0-field=from&nojs-not-0-qualifier=contains&nojs-not-0-value=jones')
    assert get_query(request) == 'text:(dummy) -from:(jones)'
    
@pytest.mark.django_db(transaction=True)
def test_group_by_thread(messages):
    sqs = SearchQuerySet().filter(email_list=1)
    sqs = sqs.order_by('tdate','date')
    print '{}'.format([ (x.pk,x.tdate,x.date) for x in sqs ])
    assert [ x.pk for x in sqs ] == [1,4,2,3]       # assert grouped by thread order

@pytest.mark.django_db(transaction=True)
def test_sort_by_subject(messages):
    sqs = SearchQuerySet().filter(email_list=1)
    sqs = sort_by_subject(sqs,None,reverse=True)
    assert [ x.pk for x in sqs ] == [3,4,2,1]
    sqs = sort_by_subject(sqs,None,reverse=False)
    assert [ x.pk for x in sqs ] == [1,2,4,3]

def test_transform():
    assert transform('invalid') == ''
    assert transform('frm') == 'frm_email'
    assert transform('-frm') == '-frm_email'

@pytest.mark.django_db(transaction=True)
def test_asf_get_facets(client,messages):
    """Ensure that calculating facet counts works and facets interact"""
    factory = RequestFactory()

    # low-levet test
    request=factory.get('/arch/search/?q=dummy')
    request.user=AnonymousUser()
    form = AdvancedSearchForm(request=request)
    sqs = SearchQuerySet()
    facets = form.get_facets(sqs)
    assert 'email_list' in facets['fields']
    assert 'frm_email' in facets['fields']

    # high-level test
    url = reverse('archive_search') + '?email_list=pubone'
    response = client.get(url)
    facets = response.context['facets']

    # ensure expected fields exist
    assert 'email_list' in facets['fields']
    assert 'frm_email' in facets['fields']

    # ensure facet totals are equal
    email_list_total = sum([ c for x,c in facets['fields']['email_list'] ])
    frm_email_total = sum([ c for x,c in facets['fields']['frm_email'] ])
    assert email_list_total == frm_email_total

    # ensure facets interact
    url = reverse('archive_search') + '?email_list=pubone&email_list=pubtwo&f_list=pubone'
    response = client.get(url)
    facets = response.context['facets']
    selected_counts = dict(facets['fields']['email_list'])
    frm_email_total = sum([ c for x,c in facets['fields']['frm_email'] ])
    assert selected_counts['pubone'] == frm_email_total

    # test that facets are sorted

@pytest.mark.django_db(transaction=True)
def test_asf_search_no_query(client,messages):
    """Test that empty search returns no results"""
    url = reverse('archive_search') + '?q='
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    text = q('#msg-list-controls').text()
    assert text.find('0 Messages') != -1

@pytest.mark.django_db(transaction=True)
def test_asf_search_simple_query(client,messages):
    url = reverse('archive_search') + '?q=database'
    response = client.get(url)
    assert response.status_code == 200

@pytest.mark.django_db(transaction=True)
def test_asf_search_email_list(client,messages):
    url = reverse('archive_search') + '?email_list=pubone'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 4

@pytest.mark.django_db(transaction=True)
def test_asf_search_date(client,messages):
    url = reverse('archive_search') + '?email_list=pubone&start_date=2014-01-01'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_asf_search_qdr(client,messages):
    url = reverse('archive_search') + '?qdr=d'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 3

@pytest.mark.django_db(transaction=True)
def test_asf_search_from(client,messages):
    url = reverse('archive_search') + '?frm=larry'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
