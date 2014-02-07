import datetime
import pytest
from django.test.client import RequestFactory
from factories import *
from mlarchive.archive.view_funcs import *
from haystack.query import SearchQuerySet

def test_chunks():
    result = list(chunks([1,2,3,4,5,6,7,8,9],3))
    assert len(result) == 3
    assert result[0] == [1,2,3]

def test_initialize_formsets():
    query = 'text:(value) -text:(negvalue)'
    reg, neg = initialize_formsets(query)
    assert len(reg.forms) == 1
    assert len(neg.forms) == 1
    assert reg.forms[0].initial['field'] == 'text'
    assert reg.forms[0].initial['value'] == 'value'
    assert neg.forms[0].initial['field'] == 'text'
    assert neg.forms[0].initial['value'] == 'negvalue'

@pytest.mark.django_db(transaction=True)
def test_get_columns():
    user = UserFactory.build()
    x = EmailListFactory.create(name='public')
    columns = get_columns(user)
    assert len(columns) == 3
    assert len(columns['active']) == 1

def test_get_export_empty(client):
    get_url = '%s?%s' % (reverse('archive_export',kwargs={'type':'mbox'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    factory = RequestFactory()
    request = factory.get(get_url)
    response = get_export(SearchQuerySet().none(),'mbox',request)
    #response = client.get(url, follow=True)
    assert response.status_code == 302
    #q = PyQuery(response.content)
    #assert len(q('li.error')) == 1
    #assert q('li.error').text() == "No messages to export."

#def test_get_export_limit(client,settings):
    # settings.EXPORT_LIMIT = 1
    # load two mesages
    # build dummy sqs

#def test_get_export_mbox(client):

#def test_get_export_maildir(client):
