import datetime
import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test.client import RequestFactory
from factories import *
from mlarchive.archive.view_funcs import *
from mlarchive.archive.forms import group_by_thread
from haystack.query import SearchQuerySet

def test_chunks():
    result = list(chunks([1,2,3,4,5,6,7,8,9],3))
    assert len(result) == 3
    assert result[0] == [1,2,3]

@pytest.mark.django_db(transaction=True)
def test_find_message_date(messages):
    sqs = SearchQuerySet().order_by('date')
    #for x in sqs: print x.date,x.object.pk,x.object.date
    last = sqs.count() - 1
    assert find_message_date(sqs,sqs[0].object) == 0        # first
    assert find_message_date(sqs,sqs[1].object) == 1        # second
    assert find_message_date(sqs,sqs[last].object) == last  # last
    # queryset of one
    msg = sqs[0].object
    sqs = SearchQuerySet().filter(msgid=msg.msgid)
    assert find_message_date(sqs,msg) == 0
    # empty queryset
    sqs = SearchQuerySet().filter(msgid='bogus')
    assert find_message_date(sqs,msg) == -1

@pytest.mark.django_db(transaction=True)
def test_find_message_date_reverse(messages):
    sqs = SearchQuerySet().order_by('-date')
    #for x in sqs: print x.date,x.object.pk,x.object.date
    last = sqs.count() - 1
    assert find_message_date(sqs,sqs[0].object,reverse=True) == 0        # first
    assert find_message_date(sqs,sqs[1].object,reverse=True) == 1        # second
    assert find_message_date(sqs,sqs[last].object,reverse=True) == last  # last
    # queryset of one
    sqs = SearchQuerySet().filter(msgid=sqs[0].msgid).order_by('-date')
    assert find_message_date(sqs,sqs[0].object,reverse=True) == 0
    # empty queryset
    msg = sqs[0].object
    sqs = SearchQuerySet().filter(msgid='bogus').order_by('-date')
    assert find_message_date(sqs,msg,reverse=True) == -1

@pytest.mark.django_db(transaction=True)
def test_find_message_gbt(messages):
    sqs = SearchQuerySet().filter(subject='New Topic')
    sqs = group_by_thread(sqs,None,None,reverse=True)
    last = sqs.count() - 1
    assert find_message_gbt(sqs,sqs[0].object,reverse=True) == 0        # first
    assert find_message_gbt(sqs,sqs[1].object,reverse=True) == 1        # second
    assert find_message_gbt(sqs,sqs[last].object,reverse=True) == last  # last
    
    # queryset of one
    sqs = SearchQuerySet().filter(msgid=sqs[0].msgid)
    sqs = group_by_thread(sqs,None,None,reverse=True)
    assert find_message_gbt(sqs,sqs[0].object,reverse=True) == 0
    
    # empty queryset
    msg = sqs[0].object
    sqs = SearchQuerySet().filter(msgid='bogus')
    sqs = group_by_thread(sqs,None,None,reverse=True)
    assert find_message_gbt(sqs,msg,reverse=True) == -1
    
    # queryset contains only one thread, msg before midpoint but has date > midpoint
    # as can happen with hierarchical display
    sqs = SearchQuerySet().filter(subject='New Topic')
    sqs = group_by_thread(sqs,None,None,reverse=True)
    msg = sqs[1].object
    assert find_message_gbt(sqs,msg,reverse=True) == 1
    
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
    setattr(request, 'session', {})
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)
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

@pytest.mark.django_db(transaction=True)
def test_get_export_url(messages):
    get_url = '%s?%s' % (reverse('archive_export',kwargs={'type':'url'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    factory = RequestFactory()
    request = factory.get(get_url)
    setattr(request, 'session', {})
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)
    response = get_export(SearchQuerySet(),'url',request)
    assert response.status_code == 200
    message = Message.objects.first()
    assert message.get_absolute_url() in response.content
    #print response.content
    #assert False

@pytest.mark.django_db(transaction=True)
def test_get_query_neighbors(messages):
    # typical
    sqs = SearchQuerySet().filter(subject='New Topic').order_by('date')
    before, after = get_query_neighbors(sqs,sqs[3].object)
    assert before == sqs[2].object
    assert after == sqs[4].object
    # first message
    before, after = get_query_neighbors(sqs,sqs[0].object)
    assert before == None
    assert after == sqs[1].object
    # one message in result set
    sqs = SearchQuerySet().filter(msgid=sqs[0].msgid)
    before, after = get_query_neighbors(sqs,sqs[0].object)
    assert before == None
    assert after == None