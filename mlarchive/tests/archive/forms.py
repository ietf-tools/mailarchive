import pytest
from django.core.urlresolvers import reverse
from django.http import HttpRequest, QueryDict
from factories import *
from haystack.query import SearchQuerySet
from mlarchive.archive.forms import *
from pprint import pprint


def test_get_base_query(client):
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
def test_get_list_info(client):
    EmailListFactory.create(name='ancp')
    EmailListFactory.create(name='alto')
    assert get_list_info(1) == 'ancp'
    assert get_list_info('ancp') == 1

@pytest.mark.django_db(transaction=True)
def test_fixture(messages):
    assert EmailList.objects.count() == 2
    assert Message.objects.count() == 2

#def test_group_by_thread(client):
    #SearchQuerySet().none()

#def test_sort_by_subject(client):

#def test_transform(client):

# test that facets are sorted

@pytest.mark.django_db(transaction=True)
def test_asf_get_facets(client):
    """Ensure that calculating facet counts works and facets interact
    - this test requires the index
    """
    elist = EmailListFactory.create(name='ancp')
    elist = EmailListFactory.create(name='alto')

    # low-levet test
    #form = AdvancedSearchForm(request=HttpRequest())
    #sqs = SearchQuerySet().filter(content='database')
    #facets = form.get_facets(sqs)

    # high-level test
    url = reverse('archive_search') + '?q=database'
    response = client.get(url)
    facets = response.context['facets']
    # pprint(response.context)

    # ensure expected fields exist
    assert 'email_list' in facets['fields']
    assert 'frm_email' in facets['fields']
    # ensure facet totals are equal
    email_list_total = sum([ c for x,c in facets['fields']['email_list'] ])
    frm_email_total = sum([ c for x,c in facets['fields']['frm_email'] ])
    assert email_list_total == frm_email_total

    # ensure facets interact
    url = reverse('archive_search') + '?q=database&f_list=ancp'
    response = client.get(url)
    facets = response.context['facets']
    selected_counts = dict(facets['fields']['email_list'])
    frm_email_total = sum([ c for x,c in facets['fields']['frm_email'] ])
    assert selected_counts['ancp'] == frm_email_total

#def test_asf_search(client):
