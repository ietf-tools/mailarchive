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
    get_export, get_query_neighbors, apply_objects, build_mbox_tar, get_thread_page_ids)
from mlarchive.archive.models import EmailList, Thread
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


# --------------------------------------------------
# get_thread_page_ids
# --------------------------------------------------

def build_thread(email_list, date, message_count=1):
    """Creates a thread with message_count messages, all dated date"""
    thread = ThreadFactory.create(email_list=email_list, date=date)
    for order in range(message_count):
        MessageFactory.create(email_list=email_list, thread=thread,
                              thread_order=order, date=date)
    return thread


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids():
    elist = EmailListFactory.create(name='pageids')
    start = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    threads = [build_thread(elist, start + datetime.timedelta(days=n)) for n in range(5)]
    # the thread itself, then the threads preceding it, most recent first
    assert get_thread_page_ids(threads[4], 3) == [threads[4].pk, threads[3].pk, threads[2].pk]
    # stops at the beginning of the list
    assert get_thread_page_ids(threads[1], 3) == [threads[1].pk, threads[0].pk]


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_whole_threads():
    '''A thread is never split, so a page may hold more than limit messages'''
    elist = EmailListFactory.create(name='pageids')
    start = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    older = build_thread(elist, start, message_count=1)
    newer = build_thread(elist, start + datetime.timedelta(days=1), message_count=5)
    assert get_thread_page_ids(newer, 3) == [newer.pk]
    assert get_thread_page_ids(newer, 6) == [newer.pk, older.pk]


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_same_date():
    '''Threads sharing a date must not be skipped. They sort by id, so the
    threads following the given one are included and those before are not
    '''
    elist = EmailListFactory.create(name='pageids')
    date = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    first = build_thread(elist, date)
    second = build_thread(elist, date)
    third = build_thread(elist, date)
    older = build_thread(elist, date - datetime.timedelta(days=1))
    assert get_thread_page_ids(first, 40) == [first.pk, second.pk, third.pk, older.pk]
    assert get_thread_page_ids(third, 40) == [third.pk, older.pk]


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_same_date_exclude_thread():
    '''include_thread=False drops only the given thread, not the rest of its
    date. This is the infinite scroll case: get_browse_results_gbt asks for the
    threads either side of one already on the page
    '''
    elist = EmailListFactory.create(name='pageids')
    date = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    newer = build_thread(elist, date + datetime.timedelta(days=1))
    first = build_thread(elist, date)
    second = build_thread(elist, date)
    third = build_thread(elist, date)
    older = build_thread(elist, date - datetime.timedelta(days=1))
    # scrolling down: second is already rendered, so is first, which sorts above it
    assert get_thread_page_ids(
        second, 40, direction='previous',
        include_thread=False) == [third.pk, older.pk]
    # scrolling up: third sorts below second and is already rendered
    assert get_thread_page_ids(
        second, 40, direction='next',
        include_thread=False) == [first.pk, newer.pk]
    # the two directions and the thread itself tile the list exactly once
    up = get_thread_page_ids(second, 40, direction='next', include_thread=False)
    down = get_thread_page_ids(second, 40, direction='previous', include_thread=False)
    assert list(reversed(up)) + [second.pk] + down == [
        newer.pk, first.pk, second.pk, third.pk, older.pk]


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_same_date_page_seam():
    '''A page and its continuation neither repeat nor skip a thread when the
    seam falls inside a group of threads sharing a date
    '''
    elist = EmailListFactory.create(name='pageids')
    date = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    tied = [build_thread(elist, date) for _ in range(4)]
    older = build_thread(elist, date - datetime.timedelta(days=1))
    expected = [t.pk for t in tied] + [older.pk]
    # a page that ends mid-tie, then the continuation from its last thread
    page = get_thread_page_ids(tied[0], 2)
    assert page == [tied[0].pk, tied[1].pk]
    rest = get_thread_page_ids(
        Thread.objects.get(pk=page[-1]), 40,
        direction='previous', include_thread=False)
    assert page + rest == expected


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_skips_empty_threads():
    '''Threads left empty by message removal must not shorten the page'''
    elist = EmailListFactory.create(name='pageids')
    start = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    oldest = build_thread(elist, start)
    empty = ThreadFactory.create(email_list=elist, date=start + datetime.timedelta(days=1))
    newest = build_thread(elist, start + datetime.timedelta(days=2))
    ids = get_thread_page_ids(newest, 2)
    assert empty.pk not in ids
    assert ids == [newest.pk, oldest.pk]


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_other_lists():
    '''Threads of other lists are never included'''
    elist = EmailListFactory.create(name='pageids')
    other = EmailListFactory.create(name='otherlist')
    start = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    older = build_thread(elist, start)
    build_thread(other, start + datetime.timedelta(hours=12))
    newest = build_thread(elist, start + datetime.timedelta(days=1))
    assert get_thread_page_ids(newest, 40) == [newest.pk, older.pk]


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_next():
    '''direction "next" walks toward newer threads'''
    elist = EmailListFactory.create(name='pageids')
    start = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    threads = [build_thread(elist, start + datetime.timedelta(days=n)) for n in range(5)]
    # nearest first, excluding the thread itself
    assert get_thread_page_ids(
        threads[0], 2, direction='next', include_thread=False) == [threads[1].pk, threads[2].pk]
    # nothing newer than the last thread
    assert get_thread_page_ids(
        threads[4], 2, direction='next', include_thread=False) == []


@pytest.mark.django_db(transaction=True)
def test_get_thread_page_ids_query_count(django_assert_num_queries):
    '''The number of queries does not grow with the size of the page'''
    elist = EmailListFactory.create(name='pageids')
    start = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
    threads = [build_thread(elist, start + datetime.timedelta(days=n)) for n in range(30)]
    with django_assert_num_queries(2):
        assert len(get_thread_page_ids(threads[-1], 20)) == 20
