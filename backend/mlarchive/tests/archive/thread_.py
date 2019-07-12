from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
from collections import namedtuple, defaultdict

import pytest
from factories import EmailListFactory, MessageFactory, ThreadFactory
from mlarchive.archive.thread import (Container, process, build_container,
    count_root_set, find_root, find_root_set, subject_is_reply,
    gather_subjects, prune_empty_containers, sort_thread, compute_thread,
    gather_siblings, get_in_reply_to, get_references_or_in_reply_to)
from mlarchive.archive.models import Message


def create_tree():
    '''Create a container tree structure to use in tests.
    1
     \
      2
      | \
      4   3
      | \
      6   5
      |
      7
    '''
    Tree = namedtuple(  # pylint: disable-msg=C0103
        'Tree',
        ['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7'])
    c1 = Container()
    c2 = Container()
    c1.child = c2
    c2.parent = c1
    c3 = Container()
    c2.child = c3
    c3.parent = c2
    c4 = Container()
    c2.next = c4
    c4.parent = c1
    c5 = Container()
    c4.child = c5
    c5.parent = c4
    c6 = Container()
    c4.next = c6
    c6.parent = c1
    c7 = Container()
    c6.next = c7
    c7.parent = c1
    return Tree(c1, c2, c3, c4, c5, c6, c7)


@pytest.mark.django_db(transaction=True)
def test_build_container():
    id_table = {}
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        msgid='001@example.com',
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        msgid='002@example.com',
        date=datetime.datetime(2016, 1, 2),
        references='<001@example.com>')
    message3 = MessageFactory.create(
        email_list=elist,
        msgid='003@example.com',
        date=datetime.datetime(2016, 1, 3),
        references='<001@example.com>')
    # simple message
    build_container(message1, id_table, 0)
    assert message1.msgid in id_table
    container1 = id_table[message1.msgid]
    assert container1.message == message1
    assert container1.parent is None
    assert container1.next is None
    assert container1.child is None
    # child of first message
    build_container(message2, id_table, 0)
    assert message2.msgid in id_table
    container2 = id_table[message2.msgid]
    assert container2.message == message2
    assert container2.parent is container1
    assert container1.child is container2
    # sibling of child
    build_container(message3, id_table, 0)
    assert message3.msgid in id_table
    container3 = id_table[message3.msgid]
    assert container3.message == message3
    assert container3.parent is container1
    assert container1.child is container3
    assert container3.next is container2


@pytest.mark.django_db(transaction=True)
def test_compute_thread():
    '''Test adding a message to existing thread'''
    elist = EmailListFactory.create()
    thread = ThreadFactory.create()
    MessageFactory.create(
        email_list=elist,
        msgid='001@example.com',
        date=datetime.datetime(2016, 1, 1),
        thread=thread,
        thread_depth=0,
        thread_order=0)
    MessageFactory.create(
        email_list=elist,
        msgid='002@example.com',
        date=datetime.datetime(2016, 1, 2),
        thread=thread,
        references='<001@example.com>',
        thread_depth=0,
        thread_order=0)
    info = compute_thread(thread)
    info_iter = iter(list(info.values()))
    thread_info = next(info_iter)
    assert thread_info.order == 0
    assert thread_info.depth == 0
    thread_info = next(info_iter)
    assert thread_info.order == 1
    assert thread_info.depth == 1


def test_container_has_ancestor():
    '''Test has_ancestor, finding elements higher up tree'''
    tree = create_tree()
    assert tree.c3.has_ancestor(tree.c1)
    assert not tree.c1.has_ancestor(tree.c3)


def test_container_has_descendent():
    '''Test has_descendent, finding elements lower in the tree'''
    # Test that we find descendent at child.next
    tree = create_tree()
    assert tree.c1.has_descendent(tree.c3)
    assert tree.c1.has_descendent(tree.c4)
    assert not tree.c3.has_descendent(tree.c1)


def test_container_has_relative():
    '''Test has_relative, finding element up or down tree'''
    tree = create_tree()
    assert tree.c2.has_relative(tree.c1)
    assert tree.c2.has_relative(tree.c3)


@pytest.mark.django_db(transaction=True)
def test_container_is_empty():
    c1 = Container()
    assert c1.is_empty()
    elist = EmailListFactory.create()
    message = MessageFactory.create(email_list=elist)
    c1.message = message
    assert not c1.is_empty()


def test_container_reverse_children():
    tree = create_tree()
    tree.c1.reverse_children()
    assert tree.c1.child == tree.c7
    assert tree.c7.next == tree.c6
    assert tree.c6.next == tree.c4
    assert tree.c4.next == tree.c2


def test_container_walk():
    tree = create_tree()
    flat = [c for c in tree.c1.walk()]
    assert flat == [tree.c1, tree.c2, tree.c3, tree.c4, tree.c5, tree.c6,
                    tree.c7]
    # check depth
    depths = [c.depth for c in tree.c1.walk()]
    assert depths == [0, 1, 2, 1, 2, 1, 1]


def test_count_root_set():
    tree = create_tree()
    root_node = Container()
    root_node.child = tree.c1
    assert count_root_set(root_node) == 1


def test_display_thread():
    pass


def test_find_root():
    tree = create_tree()
    assert find_root(tree.c5) == tree.c1


@pytest.mark.django_db(transaction=True)
def test_find_root_set():
    id_table = {}
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    build_container(message1, id_table, 0)
    root_node = find_root_set(id_table)
    assert root_node.is_empty()
    assert root_node.child.message == message1


def test_gather_siblings():
    tree = create_tree()
    siblings = defaultdict(list)
    gather_siblings(tree.c1, siblings)
    assert siblings[tree.c1] == [tree.c2, tree.c4, tree.c6, tree.c7]
    assert siblings[tree.c2] == [tree.c3]
    assert siblings[tree.c4] == [tree.c5]


@pytest.mark.django_db(transaction=True)
def test_gather_subjects():
    id_table = {}
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        subject='New product',
        base_subject='New product',
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        subject='Re: New product',
        base_subject='New product',
        date=datetime.datetime(2016, 1, 2))
    build_container(message1, id_table, 0)
    build_container(message2, id_table, 0)
    root_node = find_root_set(id_table)
    gather_subjects(root_node)
    assert root_node.child.message == message1
    assert root_node.child.child.message == message2


@pytest.mark.django_db(transaction=True)
def test_get_in_reply_to():
    elist = EmailListFactory.create()
    # test none
    message = MessageFactory.create(
        email_list=elist)
    assert get_in_reply_to(message) is None
    # test simple
    message = MessageFactory.create(
        email_list=elist,
        in_reply_to_value='<001@example.com>')
    assert get_in_reply_to(message) == '001@example.com'
    # test extra text
    irt = 'Your message of Mon, 09 Nov 2009 13:23:44 GMT. <002@example.com>'
    message = MessageFactory.create(
        email_list=elist,
        in_reply_to_value=irt)
    assert get_in_reply_to(message) == '002@example.com'


@pytest.mark.django_db(transaction=True)
def test_get_references_or_in_reply_to():
    elist = EmailListFactory.create()
    # test none
    message = MessageFactory.create(
        email_list=elist)
    assert get_references_or_in_reply_to(message) == []
    # test has refs
    message = MessageFactory.create(
        email_list=elist,
        references='<001@example.com> <002@example.com>')
    assert get_references_or_in_reply_to(message) == [
        '001@example.com', '002@example.com']
    # test no refs, has in_reply_to
    message = MessageFactory.create(
        email_list=elist,
        in_reply_to_value='<001@example.com>')
    assert get_references_or_in_reply_to(message) == ['001@example.com']


@pytest.mark.django_db(transaction=True)
def test_process_corrupt_refs_1():
    '''Scenario: within a thread, one message's reference list gets
    corrupted (list is duplicated).  This results in a loop in the
    thread container tree.  Later if a mid-list reference gets
    corrupted, a new container is created and the loop is exposed
    resulting in infinite recursion.

    De-duping references and stripping whitespace from references
    will prevent loops
    '''
    elist = EmailListFactory.create()
    MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 1))
    MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 2),
        references='<001@example.com>')
    MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 3),
        references='<001@example.com> <002@example.com>')
    MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 4),
        references='<001@example.com> <002@example.com> <003@example.com>')
    # references are duplicated here
    MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 5),
        references=' '.join([
            '<001@example.com>',
            '<002@example.com>',
            '<003@example.com>',
            '<001@example.com>',
            '<002@example.com>',
            '<003@example.com>',
            '<004@example.com>']))
    # and now a corrupted reference
    MessageFactory.create(
        email_list=elist,
        date=datetime.datetime(2016, 1, 6),
        references=' '.join([
            '<000@example.com>',
            '<001@example\t.com>',
            '<002@example.com>',
            '<000@example.com>',
            '<001@example\t.com>',
            '<002@example.com>',
            '<003@example.com>',
            '<004@example.com>']))

    queryset = Message.objects.all().order_by('date')
    assert queryset.count() == 6
    root_node = process(queryset)
    assert len(list(root_node.walk())) == 8


@pytest.mark.django_db(transaction=True)
def test_process_corrupt_refs_2():
    '''Scenario: In-reply-to message, direct thread parent, appears
    at beginning of references list, when it should appear at the end
    '''
    elist = EmailListFactory.create()
    # first message has two missing references
    MessageFactory.create(
        email_list=elist,
        msgid='000@example.com',
        date=datetime.datetime(2016, 1, 1),
        references='<missing1@example.com> <missing2@example.com>')
    # parent reference at beginning of refs
    MessageFactory.create(
        email_list=elist,
        msgid='001@example.com',
        date=datetime.datetime(2016, 1, 2),
        references=' '.join([
            '<000@example.com>',
            '<missing1@example.com>',
            '<missing2@example.com>']))

    queryset = Message.objects.all().order_by('date')
    assert queryset.count() == 2
    root_node = process(queryset)
    # we'll end up with a empty root_node and empty top-level
    # nodes with 2 messages as children
    results = [c.message.msgid for c in root_node.child.walk() if not c.is_empty()]
    assert results == ['000@example.com', '001@example.com']


@pytest.mark.django_db(transaction=True)
def test_process_corrupt_refs_3():
    '''There exist some totally bogus references in the form:

    E500A98B-DA96-49F5-9F02-C1FB694E7A29@noao.edu
    <Message> <from> <"Ulrich> <Windl">
    <Ulrich.Windl@rz.uni-regensburg.de> <of> <"Mon,>
    <20> <Jul> <2015> <13:57:02> <+0200.">
    <55ACFE2E020000A10001B2E9@gwsmtp1.uni-regensburg.de>
    <20150720185435.BDA65406057@ip-64-139-1-69.sjc.megapath.net>
    <55ADFE09020000A10001B2F6@gwsmtp1.uni-regensburg.de>
    <55ADF8D7.1000608@meinberg.de>
    <613F85B8-20E2-45AB-A1D9-1CACC5B82F64@noao.edu>
    <55AE6353.5070702@meinberg.de>
    <485FC032-3E11-4684-B578-DEF94BF82611@bsdimp.com>
    '''
    pass


@pytest.mark.django_db(transaction=True)
def test_process_in_reply_to():
    '''Test threading algorithm handling of in_reply_to header'''
    elist = EmailListFactory.create()
    # first message has two missing references
    original = MessageFactory.create(
        email_list=elist,
        msgid='001@example.com',
        date=datetime.datetime(2016, 1, 1))
    # parent reference at beginning of refs
    reply = MessageFactory.create(
        email_list=elist,
        msgid='002@example.com',
        date=datetime.datetime(2016, 1, 2),
        in_reply_to_value='<001@example.com>')
    queryset = Message.objects.all().order_by('date')
    assert queryset.count() == 2
    root_node = process(queryset)
    assert root_node.child.message == original
    assert root_node.child.child.message == reply


@pytest.mark.django_db(transaction=True)
def test_prune_empty_containers():
    tree = create_tree()
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        subject='New product',
        date=datetime.datetime(2016, 1, 1))
    for container in tree.c1.walk():
        container.message = message1
    container = Container()
    tree.c3.child = container
    container.parent = tree.c3.child
    assert len(list(tree.c1.walk())) == 8
    prune_empty_containers(tree.c1)
    assert len(list(tree.c1.walk())) == 7
    assert tree.c3.child is None


def test_sort_siblings():
    pass


@pytest.mark.django_db(transaction=True)
def test_sort_thread():
    id_table = {}
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        msgid='001@example.com',
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        msgid='002@example.com',
        references='<001@example.com>',
        date=datetime.datetime(2016, 1, 2))
    message3 = MessageFactory.create(
        email_list=elist,
        msgid='003@example.com',
        date=datetime.datetime(2016, 1, 3))
    # newest first so we get an order that will change with sort
    # (build inserts root_set memebers as it processes)
    build_container(message1, id_table, 0)
    build_container(message2, id_table, 0)
    build_container(message3, id_table, 0)
    root_node = find_root_set(id_table)
    sort_thread(root_node)
    order = [c.message.msgid for c in root_node.walk() if not c.is_empty()]
    assert order == ['003@example.com', '001@example.com', '002@example.com']


@pytest.mark.django_db(transaction=True)
def test_subject_is_reply():
    elist = EmailListFactory.create()
    message1 = MessageFactory.create(
        email_list=elist,
        subject='New product',
        date=datetime.datetime(2016, 1, 1))
    message2 = MessageFactory.create(
        email_list=elist,
        subject='Re: New product',
        date=datetime.datetime(2016, 1, 2))
    assert subject_is_reply(message2)
    assert not subject_is_reply(message1)
