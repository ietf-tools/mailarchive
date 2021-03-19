from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import QueryDict
from django.test.client import RequestFactory
from django.urls import reverse
from factories import UserFactory
from haystack.query import SearchQuerySet
from mlarchive.archive.forms import AdvancedSearchForm, get_base_query, get_cache_key
from pyquery import PyQuery

from mlarchive.archive.models import Message
from mlarchive.archive.forms import AdvancedSearchForm


def test_get_base_query():
    qd = QueryDict('q=database&f_list=saag&so=date')
    result = get_base_query(qd)
    assert isinstance(result, QueryDict)
    assert 'q' in result
    assert 'f_list' in result
    assert 'so' not in result


@pytest.mark.django_db(transaction=True)
def test_get_cache_key():
    factory = RequestFactory()
    # test regular
    url = reverse('archive_search') + '?q=database'
    request = factory.get(url)
    request.user = AnonymousUser()
    key = get_cache_key(request)
    assert key
    # sort param should not change key
    url = reverse('archive_search') + '?q=database&so=date'
    request = factory.get(url)
    request.user = AnonymousUser()
    key2 = get_cache_key(request)
    assert key == key2
    # user should change key
    url = reverse('archive_search') + '?q=database'
    request = factory.get(url)
    request.user = UserFactory.build()
    key3 = get_cache_key(request)
    assert key != key3
    # test encoded URL
    url = reverse('archive_search') + '?q=database%E2%80%8F'
    request = factory.get(url)
    request.user = AnonymousUser()
    key4 = get_cache_key(request)
    assert key4


"""
@pytest.mark.django_db(transaction=True)
def test_group_by_thread(messages):
    sqs = SearchQuerySet().filter(email_list__in=['pubone'])
    sqs = group_by_thread(sqs, None, None, reverse=True)
    print '{}'.format([(x.msgid, x.tdate, x.date) for x in sqs])
    assert [x.msgid for x in sqs] == ['a02', 'a03', 'a01', 'a04']       # assert grouped by thread order


@pytest.mark.django_db(transaction=True)
def test_sort_by_subject(messages):
   sqs = SearchQuerySet().filter(email_list=1)
   sqs = sort_by_subject(sqs,None,reverse=True)
   assert [ x.pk for x in sqs ] == [3,4,2,1]
   sqs = sort_by_subject(sqs,None,reverse=False)
   assert [ x.pk for x in sqs ] == [1,2,4,3]
"""

@pytest.mark.django_db(transaction=True)
def test_asf_get_facets(client, messages):
    """Ensure that calculating facet counts works and facets interact"""
    factory = RequestFactory()

    # low-levet test
    request = factory.get('/arch/search/?q=dummy')
    request.user = AnonymousUser()
    form = AdvancedSearchForm(request=request)
    sqs = SearchQuerySet()
    facets = form.get_facets(sqs)
    assert 'email_list' in facets['fields']
    assert 'frm_name' in facets['fields']

    # high-level test
    url = reverse('archive_search') + '?q=topic'
    response = client.get(url)
    facets = response.context['facets']

    # ensure expected fields exist
    assert 'email_list' in facets['fields']
    assert 'frm_name' in facets['fields']

    # ensure email_list correct
    assert facets['fields']['email_list'] == [('apple', 6)]

    # ensure facet totals are equal
    email_list_total = sum([c for x, c in facets['fields']['email_list']])
    frm_name_total = sum([c for x, c in facets['fields']['frm_name']])
    assert email_list_total == frm_name_total

    # ensure facets interact
    url = reverse('archive_search') + '?email_list=pubone&email_list=pubtwo&f_list=pubone'
    response = client.get(url)
    facets = response.context['facets']
    selected_counts = dict(facets['fields']['email_list'])
    frm_name_total = sum([c for x, c in facets['fields']['frm_name']])
    assert selected_counts['pubone'] == frm_name_total

    # test that facets are sorted


@pytest.mark.django_db(transaction=True)
def test_asf_search_no_query(client, messages):
    """Test that empty search returns no results"""
    url = reverse('archive_search') + '?q='
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    text = q('#msg-list-controls').text()
    assert text.find('0 Messages') != -1


@pytest.mark.django_db(transaction=True)
def test_asf_search_simple_query(client, messages):
    url = reverse('archive_search') + '?q=database'
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_asf_search_email_list(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&as=1'
    print(url)
    print(type(url))
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 4


@pytest.mark.django_db(transaction=True)
def test_asf_search_email_list_uppercase(client, messages):
    url = reverse('archive_search') + '?email_list=Pubone&as=1'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 4


@pytest.mark.django_db(transaction=True)
def test_asf_search_date(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&start_date=2014-01-01'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1


@pytest.mark.django_db(transaction=True)
def test_asf_search_qdr(client, messages):
    url = reverse('archive_search') + '?qdr=d'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    for m in Message.objects.all():
        print(m.msgid, m.date)
    # message from yesterday may not be included due to test timing
    assert len(results) in [4, 5]


@pytest.mark.django_db(transaction=True)
def test_asf_search_from(client, messages):
    url = reverse('archive_search') + '?frm=larry'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1


# --------------------------------------------------
# Low level form.search() tests
# --------------------------------------------------

def test_ensure_index(settings):
    assert settings.ELASTICSEARCH_INDEX_NAME == 'test-mail-archive'


@pytest.mark.django_db(transaction=True)
def test_form_simple(rf, client, messages):
    request = rf.get('/arch/search/?q=things')
    request.user = AnonymousUser()
    data = {'q': 'things'}
    form = AdvancedSearchForm(data=data, request=request)
    results = form.search()
    assert results.count() == 1
