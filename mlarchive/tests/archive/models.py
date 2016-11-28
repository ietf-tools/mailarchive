import pytest

import os
from factories import *
from mlarchive.archive.models import Message, EmailList


@pytest.mark.django_db(transaction=True)
def test_message_get_from_line(client):
    '''Test that non-ascii text doesn't cause errors'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)
    msg.frm = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.from_line = ''
    msg.save()
    assert msg.get_from_line()

    msg.from_line = u'studypsychologyonline\xe2\xa0@rethod.xyz'
    msg.save()
    assert msg.get_from_line()


@pytest.mark.django_db(transaction=True)
def test_notify_new_list(client, tmpdir, settings):
    settings.EXPORT_DIR = str(tmpdir)
    EmailList.objects.create(name='dummy')
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    assert os.path.exists(path)
    with open(path) as file:
        assert 'dummy' in file.read()


@pytest.mark.django_db(transaction=True)
def test_message_get_references(client):
    '''Test that message.get_references() returns reasonable
    data given variations of content'''
    elist = EmailListFactory.create()
    msg = MessageFactory.create(email_list=elist)

    # typical contents
    msg.references = u'<001-954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # no space separator
    msg.references = u'<001-954@example.com><002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # alternate separator
    msg.references = u'<001-954@example.com>\n\t<002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # extra whitespace
    msg.references = u'<001- 954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    msg.references = u'<001-954@example.com> <002-945@example\t.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected


    # extra text
    msg.references = u'[acme] durable goods <001-954@example.com> <002-945@example.com>'
    msg.save()
    expected = ['001-954@example.com', '002-945@example.com']
    assert msg.get_references() == expected

    # truncated field
    msg.references = u'<001-954@example.com> <002-945@exam'
    msg.save()
    expected = ['001-954@example.com']
    assert msg.get_references() == expected

    # duplicated references
    msg.references = ' '.join([
        '<000@example.com>',
        '<001@example.com>',
        '<000@example.com>',
        '<001@example.com>',
        '<002@example.com>'])
    msg.save()
    expected = ['000@example.com', '001@example.com', '002@example.com']
    assert msg.get_references() == expected
