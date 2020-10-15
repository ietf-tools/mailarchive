import email
import os
import pytest

from mlarchive.archive.inspectors import (ListIdSpamInspector, SpamMessage,
    SpamLevelSpamInspector, NoArchiveInspector, NoArchiveMessage)
from mlarchive.archive.mail import MessageWrapper


@pytest.mark.django_db(transaction=True)
def test_ListIdSpamInspector(client, settings):
    settings.INSPECTORS = {
        'ListIdSpamInspector': {'includes': ['mpls']}
    }
    # regular message
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail_listid.1')
    with open(path) as f:
        message = email.message_from_file(f)
    mw = MessageWrapper.from_message(message, 'mpls')
    inspector = ListIdSpamInspector(mw)
    inspector.inspect()
    # spam message
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail_listid.2')
    with open(path) as f:
        message = email.message_from_file(f)
    mw = MessageWrapper.from_message(message, 'mpls')
    inspector = ListIdSpamInspector(mw)
    with pytest.raises(SpamMessage) as excinfo:
        inspector.inspect()
    assert 'Spam' in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_SpamLevelSpamInspector(client, settings):
    settings.INSPECTORS = {
        'SpamLevelSpamInspector': {'includes': ['acme']}
    }
    # regular message
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail_spamlevel.1')
    with open(path) as f:
        message = email.message_from_file(f)
    mw = MessageWrapper.from_message(message, 'acme')
    inspector = SpamLevelSpamInspector(mw)
    inspector.inspect()
    # spam message
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail_spamlevel.2')
    with open(path) as f:
        message = email.message_from_file(f)
    mw = MessageWrapper.from_message(message, 'acme')
    inspector = SpamLevelSpamInspector(mw)
    with pytest.raises(SpamMessage) as excinfo:
        inspector.inspect()
    assert 'Spam' in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_NoArchiveInspector(client, settings):
    settings.INSPECTORS = {'NoArchiveInspector': {}}
    # regular message
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail_normal.1')
    with open(path) as f:
        message = email.message_from_file(f)
    mw = MessageWrapper.from_message(message, 'acme')
    inspector = NoArchiveInspector(mw)
    inspector.inspect()
    # spam message
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail_noarchive.1')
    with open(path) as f:
        message = email.message_from_file(f)
    mw = MessageWrapper.from_message(message, 'acme')
    inspector = NoArchiveInspector(mw)
    with pytest.raises(NoArchiveMessage) as excinfo:
        inspector.inspect()
    assert 'X-No-Archive' in str(excinfo.value)
