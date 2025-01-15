# -*- coding: utf-8 -*-
'''
This module contains pytest fixtures
'''

import datetime
import io
import os
import pytest
import subprocess
from datetime import timezone
from dateutil.relativedelta import relativedelta

from factories import EmailListFactory, ThreadFactory, MessageFactory, UserFactory
from django.conf import settings
from django.core.management import call_command
from mlarchive.archive.mail import get_base_subject
from mlarchive.archive.models import Message, Thread, Subscriber

# `pytest` automatically calls this function once when tests are run.

# collect_ignore = ["actions.py"]

'''
def pytest_configure(tmpdir_factory):
    DATA_ROOT = str(tmpdir_factory.mktemp('data'))
    settings.DATA_ROOT = DATA_ROOT
    settings.ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
    # If you have any test specific settings, you can declare them here,
    # e.g.
    # settings.PASSWORD_HASHERS = (
    #     'django.contrib.auth.hashers.MD5PasswordHasher',
    # )
    django.setup()
    # Note: In Django =< 1.6 you'll need to run this instead
    # settings.configure()
'''

# -----------------------------------
# Session Fixtures
# -----------------------------------

'''
The following two fixtures cause the test run to use a temporary
directory, /tmp/pytest-of-[user]/pytest-NNN, for data files
'''


@pytest.fixture(scope='session')
def tmp_dir(tmpdir_factory):
    """Create temporary directory for this test run"""
    tmpdir = tmpdir_factory.mktemp('data')
    yield str(tmpdir)


@pytest.fixture(autouse=True)
def data_dir(tmp_dir, settings):
    """Use temporary directory"""
    DATA_ROOT = tmp_dir
    settings.ARCHIVE_DIR = os.path.join(DATA_ROOT, 'archive')
    if not os.path.exists(settings.ARCHIVE_DIR):
        os.mkdir(settings.ARCHIVE_DIR)
    settings.EXPORT_DIR = os.path.join(DATA_ROOT, 'export')
    yield

# -----------------------------------
# Regular Fixtures
# -----------------------------------


def load_db():
    pubone = EmailListFactory.create(name='pubone')
    pubtwo = EmailListFactory.create(name='pubtwo')
    pubthree = EmailListFactory.create(name='pubthree')
    private = EmailListFactory.create(name='private', private=True)
    athread = ThreadFactory.create(date=datetime.datetime(2013, 1, 1, tzinfo=timezone.utc), email_list=pubone)
    bthread = ThreadFactory.create(date=datetime.datetime(2013, 2, 1, tzinfo=timezone.utc), email_list=pubone)
    MessageFactory.create(email_list=pubone,
                          frm='Björn',
                          thread=athread,
                          thread_order=0,
                          subject='Another message about RFC6759',
                          base_subject=get_base_subject('Another message about RFC6759'),
                          msgid='a01',
                          date=datetime.datetime(2013, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=pubone,
                          frm='Zach <zach@example.com>',
                          thread=bthread,
                          thread_order=0,
                          subject='BBQ Invitation',
                          base_subject=get_base_subject('BBQ Invitation'),
                          date=datetime.datetime(2013, 2, 1, tzinfo=timezone.utc),
                          msgid='a02',
                          to='to@amsl.com')
    MessageFactory.create(email_list=pubone,
                          frm='Arnold <arnold@example.com>',
                          thread=bthread,
                          thread_order=1,
                          subject='Re: draft-ietf-dnssec-secops',
                          base_subject=get_base_subject('Re: draft-ietf-dnssec-secops'),
                          msgid='a03',
                          date=datetime.datetime(2013, 3, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          thread_order=1,
                          frm='george@amsl.com',
                          subject='[RE] BBQ Invitation things',
                          base_subject=get_base_subject('[RE] BBQ Invitation things'),
                          date=datetime.datetime(2014, 1, 1, tzinfo=timezone.utc),
                          msgid='a04',
                          spam_score=1)
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          thread_order=2,
                          frm='larry@amsl.com',
                          subject='Party Invitation',
                          base_subject=get_base_subject('Party Invitation things'),
                          date=datetime.datetime(2014, 2, 1, tzinfo=timezone.utc),
                          msgid='a05')
    MessageFactory.create(email_list=pubtwo, subject='Trip invitation', msgid='b01')
    MessageFactory.create(email_list=pubtwo)
    date = datetime.datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for n in range(21):
        MessageFactory.create(email_list=pubthree, date=date - datetime.timedelta(days=n))

    # add thread view messages
    # NOTE: thread_order 1 has later date
    apple = EmailListFactory.create(name='apple')
    cthread = ThreadFactory.create(date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc), email_list=apple)
    MessageFactory.create(email_list=apple,
                          frm='Adam Smith <asmith@example.com>',
                          thread=cthread,
                          subject='New Topic',
                          thread_order=0,
                          msgid='c01',
                          date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=apple,
                          frm='Walter Cronkite <wcronkite@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=5,
                          msgid='c02',
                          date=datetime.datetime(2017, 1, 2, tzinfo=timezone.utc))
    MessageFactory.create(email_list=apple,
                          frm='David Johnson <djohnson@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=2,
                          msgid='c03',
                          date=datetime.datetime(2017, 1, 3, tzinfo=timezone.utc))
    MessageFactory.create(email_list=apple,
                          frm='Selma <selma@example.com',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=3,
                          msgid='c04',
                          date=datetime.datetime(2017, 1, 4, tzinfo=timezone.utc))
    MessageFactory.create(email_list=apple,
                          frm='Becky Thomspon <bthompson@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=4,
                          msgid='c05',
                          date=datetime.datetime(2017, 1, 5, tzinfo=timezone.utc))
    MessageFactory.create(email_list=apple,
                          frm='Harry Reed <hreed@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=1,
                          msgid='c06',
                          date=datetime.datetime(2017, 1, 6, tzinfo=timezone.utc))
    MessageFactory.create(email_list=private,
                          subject='private conversation',
                          msgid='p001',
                          date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=private,
                          msgid='p002',
                          date=datetime.datetime(2017, 1, 2, tzinfo=timezone.utc))

    # listnames with hyphen
    devops = EmailListFactory.create(name='dev-ops')
    MessageFactory.create(email_list=devops)

    privateops = EmailListFactory.create(name='private-ops', private=True)
    MessageFactory.create(email_list=privateops,
                          subject='privateops conversation',
                          msgid='p003')

    # private list users
    private_user = UserFactory(username='private_user')
    private.members.add(private_user)
    privateops_user = UserFactory(username='privateops_user')
    privateops.members.add(privateops_user)


@pytest.fixture()
def index_resource():
    if not Message.objects.first():
        load_db()
    # build index
    content = io.StringIO()
    call_command('rebuild_index', interactive=False, stdout=content)
    print(content.read())

    yield

    # uncomment to remove index after test
    # call_command('clear_index', interactive=False, stdout=content)
    print(content.read())


@pytest.fixture()
def messages(index_resource):
    """Load some messages into db and index for testing"""
    if not Message.objects.first():
        load_db()
    yield Message.objects.all()


@pytest.fixture()
def subscribers():
    pubone = EmailListFactory(name='pubone')
    pubtwo = EmailListFactory(name='pubtwo')
    last_month = datetime.date.today() - relativedelta(months=1)
    last_month = last_month.replace(day=1)
    Subscriber.objects.create(email_list=pubone, date=last_month, count=5)
    Subscriber.objects.create(email_list=pubtwo, date=last_month, count=3)
    Subscriber.objects.create(email_list=pubtwo, date=datetime.date(2022, 1, 1), count=2)


@pytest.fixture()
def attachment_messages_no_index(settings):
    settings.ELASTICSEARCH_SIGNAL_PROCESSOR = 'mlarchive.archive.signals.BaseSignalProcessor'
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'attachment.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'attachment_windows1252.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)
    print(content.read())
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'attachment_folded_name.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'attachment_message_rfc822.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)


@pytest.fixture()
def thread_messages():
    """Load some threads"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'thread.mail')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)


@pytest.fixture()
def export_messages():
    """Load some messages"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'export.mbox')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)


@pytest.fixture()
def urlize_messages():
    """Load some threads"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'urlize.mbox')
    call_command('load', path, listname='acme', summary=True, stdout=content)


@pytest.fixture()
def latin1_messages():
    """Load some latin1"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'latin1.mbox')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


def remove_all_files(directory):
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)


@pytest.fixture()
def search_api_messages():
    """Load messages for search_api tests"""
    # clear archive message directory
    arch_path = os.path.join(settings.ARCHIVE_DIR, 'acme')
    remove_all_files(arch_path)
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'search_api.mbox')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


@pytest.fixture()
def search_api_messages_ford():
    """Load second list for search_api"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'search_api_ford.mbox')
    call_command('load', path, listname='ford', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


@pytest.fixture()
def search_api_messages_qdr():
    """Load messages with dynamic dates for qdr tests"""
    content = io.StringIO()
    call_command('clear_index', interactive=False, stdout=content)
    public = EmailListFactory.create(name='public')
    now = datetime.datetime.now(timezone.utc)
    today = now - datetime.timedelta(hours=1)
    yesterday = now - datetime.timedelta(hours=30)
    two_weeks_ago = now - datetime.timedelta(days=14)
    six_months_ago = now - datetime.timedelta(days=180)
    last_year = now - datetime.timedelta(days=365)
    thread = ThreadFactory.create(date=last_year)
    MessageFactory.create(email_list=public,
                          thread=thread,
                          thread_order=10,
                          msgid='api301',
                          date=today)
    MessageFactory.create(email_list=public,
                          thread=thread,
                          thread_order=9,
                          msgid='api302',
                          date=yesterday)
    MessageFactory.create(email_list=public,
                          thread=thread,
                          thread_order=8,
                          msgid='api303',
                          date=two_weeks_ago)
    MessageFactory.create(email_list=public,
                          thread=thread,
                          thread_order=7,
                          msgid='api304',
                          date=six_months_ago)
    call_command('rebuild_index', interactive=False, stdout=content)


@pytest.fixture()
def private_messages():
    """Load some latin1"""
    private = EmailListFactory.create(name='private', private=True)
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'private.mbox')
    call_command('load', path, listname='private', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


@pytest.fixture()
def windows1252_messages():
    """Load some windows1252"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'windows1252.mbox')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


@pytest.fixture()
def db_only():
    '''This isn't really db_only, messages get added to index on save'''
    now = datetime.datetime.now(timezone.utc)
    yesterday = now - datetime.timedelta(hours=24)
    content = io.StringIO()
    call_command('clear_index', interactive=False, stdout=content)
    public = EmailListFactory.create(name='public')
    athread = ThreadFactory.create(date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=0,
                          msgid='x001',
                          date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=0,
                          msgid='x002',
                          date=datetime.datetime(2018, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=0,
                          msgid='x003',
                          date=yesterday)


@pytest.fixture()
def thread_messages_db_only():
    '''db_only doesn't work. do to signal?'''
    public = EmailListFactory.create(name='public')
    athread = ThreadFactory.create(date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc))
    bthread = ThreadFactory.create(date=datetime.datetime(2017, 2, 1, tzinfo=timezone.utc))
    cthread = ThreadFactory.create(date=datetime.datetime(2017, 3, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=0,
                          msgid='x001',
                          date=datetime.datetime(2017, 1, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=1,
                          msgid='x002',
                          date=datetime.datetime(2017, 2, 15, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=2,
                          msgid='x003',
                          date=datetime.datetime(2017, 1, 15, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=bthread,
                          thread_order=0,
                          msgid='x004',
                          date=datetime.datetime(2017, 2, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=bthread,
                          thread_order=1,
                          msgid='x005',
                          date=datetime.datetime(2017, 3, 15, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=cthread,
                          thread_order=0,
                          msgid='x006',
                          date=datetime.datetime(2017, 3, 1, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=cthread,
                          thread_order=1,
                          msgid='x007',
                          date=datetime.datetime(2017, 3, 20, tzinfo=timezone.utc))
    MessageFactory.create(email_list=public,
                          thread=cthread,
                          thread_order=2,
                          msgid='x008',
                          date=datetime.datetime(2017, 3, 10, tzinfo=timezone.utc))

    # set first
    for thread in Thread.objects.all():
        thread.set_first()


@pytest.fixture()
def attachment_messages_db_only():
    pass


@pytest.fixture()
def static_list():
    """Load messages over multiple years for testing static index pages.
    Use STATIC_INDEX_YEAR_MINIMUM = 20 in tests
    """
    public = EmailListFactory.create(name='public')
    date = datetime.datetime(2015, 6, 30, tzinfo=timezone.utc)
    for n in range(15):
        MessageFactory.create(email_list=public, date=date - datetime.timedelta(days=n))
    date = datetime.datetime(2017, 12, 30, tzinfo=timezone.utc)
    for n in range(25):
        MessageFactory.create(email_list=public, date=date - datetime.timedelta(days=n))
    # set thread.first
    for thread in Thread.objects.all():
        thread.email_list = public
        thread.set_first()
    yield public


@pytest.fixture()
def query_messages():
    """Load some threads"""
    content = io.StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'query_acme.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'query_star.mail')
    call_command('load', path, listname='star', summary=True, stdout=content)
    yield Message.objects.all()


@pytest.fixture()
def static_dir(data_dir):
    path = os.path.join(settings.STATIC_INDEX_DIR, 'public')
    if not os.path.isdir(path):
        os.makedirs(path)
    yield settings.STATIC_INDEX_DIR
    # teardown


@pytest.fixture()
def clear_index():
    """A fixture to clear the Elasticsearch index before running the test"""
    content = io.StringIO()
    call_command('clear_index', interactive=False, stdout=content)


@pytest.fixture()
def users():
    """A fixture with various types of Users for testing"""
    staff_user = UserFactory(
        username='staff@example.com',
        email='staff@example.com',
        password='password',
        is_staff=True)
    unprivileged_user = UserFactory(
        username='unprivileged@example.com',
        email='unprivileged@example.com',
        password='password',
        is_staff=False)

# --------------------------------------------------
# Celery Fixtures
# --------------------------------------------------


@pytest.fixture()
def celery_service():
    try:
        subprocess.check_call(['celery', 'status'])
    except subprocess.CalledProcessError:
        pytest.skip('No Celery service found')


@pytest.fixture(scope='session')
def celery_config():
    return {'broker_url': 'amqp://'}
