# -*- coding: utf-8 -*-
'''
This module contains pytest fixtures
'''

from __future__ import absolute_import, division, print_function, unicode_literals

# for Python 2/3 compatability
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import datetime
import os
import pytest
import subprocess

from factories import EmailListFactory, ThreadFactory, MessageFactory
from django.conf import settings
from django.core.management import call_command
from mlarchive.archive.mail import get_base_subject
from mlarchive.archive.models import Message, Thread

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
    athread = ThreadFactory.create(date=datetime.datetime(2013, 1, 1), email_list=pubone)
    bthread = ThreadFactory.create(date=datetime.datetime(2013, 2, 1), email_list=pubone)
    MessageFactory.create(email_list=pubone,
                          frm='Björn',
                          thread=athread,
                          thread_order=0,
                          subject='Another message about RFC6759',
                          base_subject=get_base_subject('Another message about RFC6759'),
                          msgid='a01',
                          date=datetime.datetime(2013, 1, 1))
    MessageFactory.create(email_list=pubone,
                          frm='Zach <zach@example.com>',
                          thread=bthread,
                          thread_order=0,
                          subject='BBQ Invitation',
                          base_subject=get_base_subject('BBQ Invitation'),
                          date=datetime.datetime(2013, 2, 1),
                          msgid='a02',
                          to='to@amsl.com')
    MessageFactory.create(email_list=pubone,
                          frm='Arnold <arnold@example.com>',
                          thread=bthread,
                          thread_order=1,
                          subject='Re: draft-ietf-dnssec-secops',
                          base_subject=get_base_subject('Re: draft-ietf-dnssec-secops'),
                          msgid='a03',
                          date=datetime.datetime(2013, 3, 1))
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          thread_order=1,
                          frm='larry@amsl.com',
                          subject='[RE] BBQ Invitation things',
                          base_subject=get_base_subject('[RE] BBQ Invitation things'),
                          date=datetime.datetime(2014, 1, 1),
                          msgid='a04',
                          spam_score=1)
    MessageFactory.create(email_list=pubtwo)
    MessageFactory.create(email_list=pubtwo)
    date = datetime.datetime.now().replace(second=0, microsecond=0)
    for n in range(21):
        MessageFactory.create(email_list=pubthree, date=date - datetime.timedelta(days=n))

    # add thread view messages
    # NOTE: thread_order 1 has later date
    apple = EmailListFactory.create(name='apple')
    cthread = ThreadFactory.create(date=datetime.datetime(2017, 1, 1), email_list=apple)
    MessageFactory.create(email_list=apple,
                          frm='Adam Smith <asmith@example.com>',
                          thread=cthread,
                          subject='New Topic',
                          thread_order=0,
                          msgid='c01',
                          date=datetime.datetime(2017, 1, 1))
    MessageFactory.create(email_list=apple,
                          frm='Walter Cronkite <wcronkite@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=5,
                          msgid='c02',
                          date=datetime.datetime(2017, 1, 2))
    MessageFactory.create(email_list=apple,
                          frm='David Johnson <djohnson@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=2,
                          msgid='c03',
                          date=datetime.datetime(2017, 1, 3))
    MessageFactory.create(email_list=apple,
                          frm='Selma <selma@example.com',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=3,
                          msgid='c04',
                          date=datetime.datetime(2017, 1, 4))
    MessageFactory.create(email_list=apple,
                          frm='Becky Thomspon <bthompson@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=4,
                          msgid='c05',
                          date=datetime.datetime(2017, 1, 5))
    MessageFactory.create(email_list=apple,
                          frm='Harry Reed <hreed@example.com>',
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=1,
                          msgid='c06',
                          date=datetime.datetime(2017, 1, 6))
    MessageFactory.create(email_list=private, date=datetime.datetime(2017, 1, 1))
    MessageFactory.create(email_list=private, date=datetime.datetime(2017, 1, 2))

    # listnames with hyphen
    devops = EmailListFactory.create(name='dev-ops')
    MessageFactory.create(email_list=devops)

    privateops = EmailListFactory.create(name='private-ops', private=True)
    MessageFactory.create(email_list=privateops)


@pytest.fixture()
def index_resource():
    if not Message.objects.first():
        load_db()
    # build index
    content = StringIO()
    call_command('update_index', stdout=content)
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
def attachment_messages_no_index(settings):
    settings.HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.BaseSignalProcessor'
    content = StringIO()
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
    content = StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'thread.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)


@pytest.fixture()
def urlize_messages():
    """Load some threads"""
    content = StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'urlize.mbox')
    call_command('load', path, listname='acme', summary=True, stdout=content)


@pytest.fixture()
def latin1_messages():
    """Load some latin1"""
    content = StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'latin1.mbox')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


@pytest.fixture()
def windows1252_messages():
    """Load some windows1252"""
    content = StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'windows1252.mbox')
    call_command('clear_index', interactive=False, stdout=content)
    call_command('load', path, listname='acme', summary=True, stdout=content)
    print(content.read())
    assert Message.objects.count() > 0


@pytest.fixture()
def thread_messages_db_only():
    public = EmailListFactory.create(name='public')
    athread = ThreadFactory.create(date=datetime.datetime(2017, 1, 1))
    bthread = ThreadFactory.create(date=datetime.datetime(2017, 2, 1))
    cthread = ThreadFactory.create(date=datetime.datetime(2017, 3, 1))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=0,
                          msgid='x001',
                          date=datetime.datetime(2017, 1, 1))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=1,
                          msgid='x002',
                          date=datetime.datetime(2017, 2, 15))
    MessageFactory.create(email_list=public,
                          thread=athread,
                          thread_order=2,
                          msgid='x003',
                          date=datetime.datetime(2017, 1, 15))
    MessageFactory.create(email_list=public,
                          thread=bthread,
                          thread_order=0,
                          msgid='x004',
                          date=datetime.datetime(2017, 2, 1))
    MessageFactory.create(email_list=public,
                          thread=bthread,
                          thread_order=1,
                          msgid='x005',
                          date=datetime.datetime(2017, 3, 15))
    MessageFactory.create(email_list=public,
                          thread=cthread,
                          thread_order=0,
                          msgid='x006',
                          date=datetime.datetime(2017, 3, 1))
    MessageFactory.create(email_list=public,
                          thread=cthread,
                          thread_order=1,
                          msgid='x007',
                          date=datetime.datetime(2017, 3, 20))
    MessageFactory.create(email_list=public,
                          thread=cthread,
                          thread_order=2,
                          msgid='x008',
                          date=datetime.datetime(2017, 3, 10))

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
    date = datetime.datetime(2015, 6, 30)
    for n in range(15):
        MessageFactory.create(email_list=public, date=date - datetime.timedelta(days=n))
    date = datetime.datetime(2017, 12, 30)
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
    content = StringIO()
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
    return {
        'broker_url': 'amqp://',
        #'result_backend': 'redis://'
    }
