import pytest
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
def test_get_list_info():
    EmailListFactory.create(name='ancp')
    EmailListFactory.create(name='alto')
    assert get_list_info(1) == 'ancp'
    assert get_list_info('ancp') == 1

@pytest.mark.django_db(transaction=True)
def test_group_by_thread(messages):
    sqs = SearchQuerySet().filter(email_list=1)
    sqs = group_by_thread(sqs,None,None,reverse=True)
    assert [ x.pk for x in sqs ] == [4,2,3,1]       # assert grouped by thread order

@pytest.mark.django_db(transaction=True)
def test_sort_by_subject(messages):
    sqs = SearchQuerySet().filter(email_list=1)
    sqs = sort_by_subject(sqs,None,reverse=True)
    assert [ x.pk for x in sqs ] == [3,4,1,2]
    sqs = sort_by_subject(sqs,None,reverse=False)
    assert [ x.pk for x in sqs ] == [2,1,4,3]

def test_transform():
    assert transform('invalid') == ''
    assert transform('frm') == 'frm_email'
    assert transform('-frm') == '-frm_email'

@pytest.mark.django_db(transaction=True)
def test_asf_get_facets(client,messages):
    """Ensure that calculating facet counts works and facets interact"""
    factory = RequestFactory()

    # low-levet test
    form = AdvancedSearchForm(request=factory.get('/arch/search/?q=dummy'))
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
    url = reverse('archive_search') + '?email_list=pubone,pubtwo&f_list=pubone'
    response = client.get(url)
    facets = response.context['facets']
    selected_counts = dict(facets['fields']['email_list'])
    frm_email_total = sum([ c for x,c in facets['fields']['frm_email'] ])
    assert selected_counts['pubone'] == frm_email_total

    # test that facets are sorted

@pytest.mark.django_db(transaction=True)
def test_asf_search_no_query(client,messages):
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
    assert len(results) == 2

@pytest.mark.django_db(transaction=True)
def test_asf_search_from(client,messages):
    url = reverse('archive_search') + '?frm=larry'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
