import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from factories import EmailListFactory, ThreadFactory, MessageFactory, UserFactory
from pyquery import PyQuery
from mlarchive.archive.models import Message, Thread
from mlarchive.archive.ajax import (get_query_results, get_browse_results,
    get_browse_results_gbt, get_browse_results_date)
import os
import shutil


@pytest.mark.django_db(transaction=True)
def test_ajax_admin_action(client):
    UserFactory.create(is_superuser=True)
    elist = EmailListFactory.create(name='public')
    msg = MessageFactory.create(email_list=elist)
    client.login(username='admin', password='admin')
    url = reverse('ajax_admin_action')
    data = {'action': 'remove_selected', 'ids': '%s' % msg.pk}
    response = client.post(url, data)
    assert response.status_code == 200
    assert Message.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_ajax_get_msg(client):
    publist = EmailListFactory.create(name='public')
    prilist = EmailListFactory.create(name='private', private=True)
    user = UserFactory.create(is_superuser=True)
    prilist.members.add(user)
    thread = ThreadFactory.create()
    msg = MessageFactory.create(email_list=publist, thread=thread, hashcode='00001')
    primsg = MessageFactory.create(email_list=prilist, thread=thread, hashcode='00002')
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    for m in (msg, primsg):
        if not os.path.exists(os.path.dirname(m.get_file_path())):
            os.makedirs(os.path.dirname(m.get_file_path()))
        shutil.copyfile(path, m.get_file_path())

    url = '%s/?id=%s' % (reverse('ajax_get_msg'), msg.pk)
    response = client.get(url)
    assert response.status_code == 200
    assert response.content.find('This is a test') != -1

    # test unauthorized access to restricted Message
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), primsg.pk)
    response = client.get(url)
    assert response.status_code == 403

    # test authorized access to restricted Message
    assert client.login(username='admin', password='admin')
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), primsg.pk)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_ajax_get_msg_thread_links(client, thread_messages):
    msg = Message.objects.get(msgid='00002@example.com')
    url = '%s/?id=%s' % (reverse('ajax_get_msg'), msg.pk)
    response = client.get(url)
    assert response.status_code == 200

    q = PyQuery(response.content)
    assert q('#message-thread').length == 1
    assert q('.thread-snippet li').length == 4


@pytest.mark.django_db(transaction=True)
def test_ajax_get_messages(client, messages):
    # run initial query to setup cache
    url = '%s/?email_list=pubone&email_list=pubtwo' % reverse('archive_search')
    response = client.get(url)
    assert response.status_code == 200
    # for x in response.context['results']:
    #     print type(x)
    assert len(response.context['results']) == 6
    q = PyQuery(response.content)
    id = q('.msg-list').attr('data-queryid')

    print id,
    print cache.get(id)

    # test successful get_messages call
    url = '%s/?qid=%s&referenceitem=2&direction=next' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('.xtr')) > 1

    # test end of results
    url = '%s/?qid=%s&referenceitem=40&direction=next' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 204

    # test expired cache
    cache.delete(id)
    url = '%s/?qid=%s&referenceitem=20&direction=next' % (reverse('ajax_messages'), id)
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_ajax_get_messages_browse(client, messages):
    message = Message.objects.filter(email_list__name='pubone').order_by('-date').first()
    url = '{}/?qid=&referenceitem=1&browselist=pubone&referenceid={}&gbt=&direction=next'.format(
        reverse('ajax_messages'), message.pk)
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 3


@pytest.mark.django_db(transaction=True)
def test_ajax_get_messages_browse_private_unauth(client, messages):
    '''Test that unauthorized person cannot retrieve private messages'''
    message = Message.objects.filter(email_list__name='private').order_by('-date').first()
    url = '{}/?qid=&referenceitem=1&browselist=private&referenceid={}&gbt=&direction=next'.format(
        reverse('ajax_messages'), message.pk)
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_ajax_get_messages_browse_gbt(client, messages):
    threads = Thread.objects.filter(first__email_list__name='pubone').order_by('-date')
    messages = threads[1].message_set.all().order_by('thread_order')
    last_message = threads[0].message_set.all().order_by('thread_order').last()
    url = '{}/?qid=&referenceitem=1&browselist=pubone&referenceid={}&gbt=1&direction=next'.format(
        reverse('ajax_messages'), last_message.pk)
    response = client.get(url)
    print threads[0].pk
    print threads[0].get_next()
    for m in threads[0].message_set.all().order_by('thread_order'): print m.date, m.pk
    print threads[1].pk
    for m in threads[1].message_set.all().order_by('thread_order'): print m.date, m.pk
    assert response.status_code == 200
    assert len(response.context['results']) == messages.count()

    # assert proper order
    print [(m.pk, m.thread_order) for m in messages]
    assert [r.object.pk for r in response.context['results']] == [m.pk for m in messages]


@pytest.mark.django_db(transaction=True)
def test_get_query_results(client, messages):
    # run initial query to setup cache
    url = '%s/?email_list=pubthree' % reverse('archive_search')
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == settings.HAYSTACK_SEARCH_RESULTS_PER_PAGE
    q = PyQuery(response.content)
    qid = q('.msg-list').attr('data-queryid')
    query = cache.get(qid)
    messages = Message.objects.filter(email_list__name='pubthree').order_by('-date')
    results = get_query_results(query=query, referenceitem=10, direction='next')
    # assert we get the remaining messages ordered by date descending
    assert len(results) == 11
    assert [r.object.pk for r in results] == [m.pk for m in messages[10:]]


@pytest.mark.django_db(transaction=True)
def test_get_browse_results(client, messages):
    '''Simple test of high level function'''
    message = Message.objects.filter(email_list__name='pubthree').order_by('-date').first()
    results = get_browse_results(referenceid=message.pk, direction='next', gbt=None)
    assert results


@pytest.mark.django_db(transaction=True)
def test_get_browse_results_gbt(client, thread_messages_db_only):
    message = Message.objects.get(msgid='x008')
    results = get_browse_results_gbt(reference_message=message, direction='next')
    assert len(results) == 5
    assert [r.object.msgid for r in results] == ['x004', 'x005', 'x001', 'x002', 'x003']


@pytest.mark.django_db(transaction=True)
def test_get_browse_results_date(client, messages):
    messages = Message.objects.filter(email_list__name='pubthree').order_by('-date')
    results = get_browse_results_date(reference_message=messages[9], direction='next')
    print messages.count()
    assert len(results) == 11
    assert [r.object.pk for r in results] == [m.pk for m in messages[10:]]
