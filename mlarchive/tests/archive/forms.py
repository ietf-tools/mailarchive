import pytest
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from factories import *
from haystack.query import SearchQuerySet
from mlarchive.archive.forms import *

@pytest.mark.django_db(transaction=True)
def test_get_facets(client):
    '''Ensure that calculating facet counts works and facets interact
    - this test requires the index
    '''
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