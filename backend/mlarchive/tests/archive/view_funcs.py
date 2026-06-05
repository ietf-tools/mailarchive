import datetime
import glob
import io
import mailbox
import os
import pytest
import tarfile
from datetime import timezone
from factories import EmailListFactory, ThreadFactory, MessageFactory, UserFactory

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from django.conf import settings
from django.urls import reverse
from django.utils.encoding import smart_str

from mlarchive.archive.view_funcs import (chunks, initialize_formsets, get_columns,
    get_export, get_query_neighbors, apply_objects, build_mbox_tar)
from mlarchive.archive.models import EmailList
from mlarchive.utils.test_utils import get_request

from mlarchive.archive.view_funcs import get_message_index
from mlarchive.archive.backends.elasticsearch import ESBackend


def get_search():
    client = ESBackend().client
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    return s


def get_empty_search():
    client = ESBackend().client
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    s = s.query('match', subject='')
    return s


def test_chunks():
    result = list(chunks([1, 2, 3, 4, 5, 6, 7, 8, 9], 3))
    assert len(result) == 3
    assert result[0] == [1, 2, 3]


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
    EmailListFactory.create(name='secret', private=True)
    private = EmailListFactory.create(name='private', private=True)
    private.members.add(user)
    request = get_request(user=user)
    #request = get_request(user=AnonymousUser())
    columns = get_columns(request)
    from mlarchive.archive.utils import get_noauth, get_lists_for_user
    q = EmailList.objects.all().exclude(name__in=get_noauth(user))
    print(get_lists_for_user(user))
    print(user.is_authenticated)
    print(q.count(), q[0].name, q[1].name)
    print(get_noauth(user))
    print(user.is_superuser)
    print(columns)
    print(EmailList.objects.all())
    assert len(columns) == 3
    assert len(columns['active']) == 1
    assert len(columns['private']) == 1


@pytest.mark.django_db(transaction=True)
def test_get_export_empty(client, messages):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    request = get_request(url=url)
    response = get_export(get_empty_search(), 'mbox', request)
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_get_export_limit_mbox(client, messages, settings):
    settings.EXPORT_LIMIT = 1
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    request = get_request(url=url)
    response = get_export(get_search(), 'mbox', request)
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_get_export_limit_url(client, messages, settings):
    settings.EXPORT_LIMIT = 1
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'url'}), 'q=database')
    redirect_url = '%s?%s' % (reverse('archive_search'), 'q=database')
    request = get_request(url=url)
    response = get_export(get_search(), 'url', request)
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
def test_get_export_superuser_limit(client, admin_client, thread_messages, settings):
    settings.EXPORT_LIMIT = 1
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
    search = get_search()
    search = search.query('term', email_list='acme')

    # validate response is valid tarball with mbox file, with 4 messages
    response = get_export(search, 'mbox', request)
    assert response.status_code == 200
    assert response.has_header('content-disposition')
    tar = tarfile.open(mode="r:gz", fileobj=io.BytesIO(response.content))
    assert len(tar.getmembers()) == 1
    path = tmpdir.mkdir('sub').strpath
    tar.extractall(path)
    mboxs = glob.glob(os.path.join(path, '*', 'acme', '*.mbox'))
    mbox = mailbox.mbox(mboxs[0])
    assert len(mbox) == 4


@pytest.mark.django_db(transaction=True)
def test_build_mbox_tar_from_sorted(tmpdir):
    """build_mbox_tar loses messages when results are sorted by a non-date field.

    With frm-sorted results like [Aaron/Jan, Bob/Feb, Charlie/Jan], the same
    archive path (acme/2024-01.mbox) is added to the tar twice. On extraction
    the second entry overwrites the first, silently dropping messages.
    """
    acme = EmailListFactory.create(name='acme_export')
    thread_jan = ThreadFactory.create(
        date=datetime.datetime(2024, 1, 1, tzinfo=timezone.utc), email_list=acme)
    thread_feb = ThreadFactory.create(
        date=datetime.datetime(2024, 2, 1, tzinfo=timezone.utc), email_list=acme)

    m1 = MessageFactory.create(
        email_list=acme, frm='Aaron <a@example.com>',
        thread=thread_jan, thread_order=0, msgid='exp01',
        date=datetime.datetime(2024, 1, 1, tzinfo=timezone.utc))
    m2 = MessageFactory.create(
        email_list=acme, frm='Bob <b@example.com>',
        thread=thread_feb, thread_order=0, msgid='exp02',
        date=datetime.datetime(2024, 2, 1, tzinfo=timezone.utc))
    m3 = MessageFactory.create(
        email_list=acme, frm='Charlie <c@example.com>',
        thread=thread_jan, thread_order=1, msgid='exp03',
        date=datetime.datetime(2024, 1, 15, tzinfo=timezone.utc))

    # Create the message files that get_file_path() points to
    list_dir = os.path.join(settings.ARCHIVE_DIR, acme.name)
    os.makedirs(list_dir, exist_ok=True)
    for msg, subject in [(m1, 'January A'), (m2, 'February B'), (m3, 'January C')]:
        with open(msg.get_file_path(), 'wb') as f:
            f.write(
                f'From sender@example.com Mon Jan  1 00:00:00 2024\n'
                f'Subject: {subject}\n\nBody\n\n'.encode()
            )

    class FakeResult:
        def __init__(self, msg):
            self.object = msg

    # Sorted by frm: Aaron (Jan), Bob (Feb), Charlie (Jan) — months interleaved
    results = [FakeResult(m1), FakeResult(m2), FakeResult(m3)]

    tardata = io.BytesIO()
    tar = tarfile.open(fileobj=tardata, mode='w:gz')
    tar = build_mbox_tar(results, tar, 'test_export')
    tar.close()
    tardata.seek(0)

    extract_path = str(tmpdir.mkdir('extracted'))
    tar2 = tarfile.open(mode='r:gz', fileobj=tardata)
    tar2.extractall(extract_path)

    mbox_files = glob.glob(os.path.join(extract_path, '**', '*.mbox'), recursive=True)
    total_messages = sum(len(mailbox.mbox(p)) for p in mbox_files)

    assert total_messages == 3, (
        f'Expected 3 messages but got {total_messages} — '
        'duplicate tar entries caused by non-date sort order'
    )


@pytest.mark.django_db(transaction=True)
def test_get_export_mbox_latin1(client, latin1_messages, tmpdir):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'mbox'}), 'q=anvil')
    request = get_request(url=url)
    EmailList.objects.get(name='acme')
    search = get_search()
    search = search.query('term', email_list='acme')

    # validate response is valid tarball with mbox file, with 4 messages
    response = get_export(search, 'mbox', request)
    assert response.status_code == 200
    assert response.has_header('content-disposition')
    tar = tarfile.open(mode="r:gz", fileobj=io.BytesIO(response.content))
    assert len(tar.getmembers()) == 1
    path = tmpdir.mkdir('sub').strpath
    print(path)
    tar.extractall(path)
    mboxs = glob.glob(os.path.join(path, '*', 'acme', '*.mbox'))
    mbox = mailbox.mbox(mboxs[0])
    assert len(mbox) == 1


@pytest.mark.django_db(transaction=True)
def test_get_export_maildir(client, thread_messages, tmpdir):
    url = '%s?%s' % (reverse('archive_export', kwargs={'type': 'maildir'}), 'q=anvil')
    request = get_request(url=url)
    EmailList.objects.get(name='acme')
    search = get_search()
    search = search.query('term', email_list='acme')

    # validate response is valid tarball with maildir directory and 4 messages
    response = get_export(search, 'maildir', request)
    assert response.status_code == 200
    assert response.has_header('content-disposition')
    tar = tarfile.open(mode="r:gz", fileobj=io.BytesIO(response.content))
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
    search = get_search()
    search = search.query('term', email_list='pubone')
    response = get_export(search, 'url', request)
    assert response.status_code == 200
    search_response = search.execute()
    apply_objects(search_response.hits)
    assert search_response[0].object.get_absolute_url() in smart_str(response.content)


@pytest.mark.django_db(transaction=True)
def test_get_query_neighbors(messages):
    # typical
    search = get_search()
    search = search.query('match', subject='New Topic')
    search = search.sort('date')
    response = search.execute()
    apply_objects(response.hits)
    for r in response:
        print(r.date, r.subject)
    before, after = get_query_neighbors(search, response[3].object)
    assert before == response[2].object
    assert after == response[4].object
    # first message
    print(search.to_dict())
    i = get_message_index(search, response[0].object)
    print('index: {}'.format(i))
    before, after = get_query_neighbors(search, response[0].object)
    assert before is None
    assert after == response[1].object
    # one message in result set
    search = get_search()
    search = search.query('match', msgid=response[0].msgid)
    response = search.execute()
    apply_objects(response.hits)
    before, after = get_query_neighbors(search, response[0].object)
    assert before is None
    assert after is None
