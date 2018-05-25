import email
import glob
import mailbox
import os
import pytest
import tarfile
from factories import EmailListFactory, UserFactory
from StringIO import StringIO

from haystack.query import SearchQuerySet
from django.http import HttpResponse
from django.urls import reverse

from mlarchive.archive.view_funcs import (chunks, initialize_formsets, get_columns,
    get_export, get_query_neighbors, custom_search_view_factory)
from mlarchive.archive.models import EmailList
from mlarchive.utils.test_utils import get_request


def test_chunks():
    result = list(chunks([1, 2, 3, 4, 5, 6, 7, 8, 9], 3))
    assert len(result) == 3
    assert result[0] == [1, 2, 3]


def test_custom_search_view_factory():
    request = get_request()
    view = custom_search_view_factory()
    response = view(request)
    assert isinstance(response, HttpResponse)
    assert response.status_code == 200


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
    user = UserFactory.create()
    EmailListFactory.create(name='public')
    private = EmailListFactory.create(name='private', private=True)
    private.members.add(user)
    request = get_request(user=user)
    columns = get_columns(request)
    assert len(columns) == 3
    assert len(columns['active']) == 1
    assert len(columns['private']) == 1


def test_get_export_empty(client):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    request = get_request(url=url)
    response = get_export(SearchQuerySet().none(), 'mbox', request)
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_get_export_limit_mbox(client, messages, settings):
    settings.EXPORT_LIMIT = 1
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    request = get_request(url=url)
    response = get_export(SearchQuerySet(), 'mbox', request)
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_get_export_limit_url(client, messages, settings):
    settings.EXPORT_LIMIT = 1
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'url'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    request = get_request(url=url)
    response = get_export(SearchQuerySet(), 'url', request)
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_get_export_anonymous_limit(client, admin_client, thread_messages, settings):
    settings.ANONYMOUS_EXPORT_LIMIT = 1
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=anvil')
    response = client.get(url)
    assert response.status_code == 302
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_get_export_mbox(client, thread_messages, tmpdir):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=anvil')
    request = get_request(url=url)
    EmailList.objects.get(name='acme')
    sqs = SearchQuerySet().filter(email_list__in=['acme'])

    # validate response is valid tarball with mbox file, with 4 messages
    response = get_export(sqs, 'mbox', request)
    assert response.status_code == 200
    assert response.has_header('content-disposition')
    tar = tarfile.open(mode="r:gz", fileobj=StringIO(response.content))
    assert len(tar.getmembers()) == 1
    path = tmpdir.mkdir('sub').strpath
    tar.extractall(path)
    mboxs = glob.glob(os.path.join(path, '*', 'acme', '*.mbox'))
    mbox = mailbox.mbox(mboxs[0])
    assert len(mbox) == 4


@pytest.mark.django_db(transaction=True)
def test_get_export_maildir(client, thread_messages, tmpdir):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'maildir'}), 'q=anvil')
    request = get_request(url=url)
    EmailList.objects.get(name='acme')
    sqs = SearchQuerySet().filter(email_list__in=['acme'])

    # validate response is valid tarball with maildir directory and 4 messages
    response = get_export(sqs, 'maildir', request)
    assert response.status_code == 200
    assert response.has_header('content-disposition')
    tar = tarfile.open(mode="r:gz", fileobj=StringIO(response.content))
    assert len(tar.getmembers()) == 4
    path = tmpdir.mkdir('sub').strpath
    tar.extractall(path)
    files = glob.glob(os.path.join(path, '*', 'acme', '*'))
    # print files
    assert len(files) == 4
    # with open(files[0]) as fp:
    #    msg = email.message_from_file(fp)
    # assert msg['message-id'] == '<00001@example.com>'


@pytest.mark.django_db(transaction=True)
def test_get_export_url(messages):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'url'}), 'q=message')
    request = get_request(url=url)
    sqs = SearchQuerySet().filter(email_list__in=['pubone'])
    response = get_export(sqs, 'url', request)
    assert response.status_code == 200
    assert sqs[0].object.get_absolute_url() in response.content


@pytest.mark.django_db(transaction=True)
def test_get_query_neighbors(messages):
    # typical
    sqs = SearchQuerySet().filter(subject='New Topic').order_by('date')
    before, after = get_query_neighbors(sqs, sqs[3].object)
    assert before == sqs[2].object
    assert after == sqs[4].object
    # first message
    before, after = get_query_neighbors(sqs, sqs[0].object)
    assert before is None
    assert after == sqs[1].object
    # one message in result set
    sqs = SearchQuerySet().filter(msgid=sqs[0].msgid)
    before, after = get_query_neighbors(sqs, sqs[0].object)
    assert before is None
    assert after is None
