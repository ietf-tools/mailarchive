# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest

from django.urls import reverse
from django.utils.encoding import smart_text
from factories import EmailListFactory, UserFactory
from mlarchive.archive.models import Message

from pyquery import PyQuery


# --------------------------------------------------
# Authentication
# --------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_not_logged_browse(client):
    'Test that a not logged in user does not see any private lists in browse menu'
    EmailListFactory.create(name='private', private=True)
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#private-lists li')) == 0


@pytest.mark.django_db(transaction=True)
def test_unauth_browse(client):
    '''Test that a logged in user does not see private lists they aren't
    a member of.
    '''
    EmailListFactory.create(name='private', private=True)
    UserFactory.create()
    assert client.login(username='admin', password='admin')
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(response.content)
    assert len(q('#private-lists li')) == 0


@pytest.mark.django_db(transaction=True)
def test_auth_browse(client):
    '''Test that a logged in user does see private lists they are
    a member of.
    '''
    elist = EmailListFactory.create(name='private', private=True)
    user = UserFactory.create()
    assert client.login(username='admin', password='admin')
    elist.members.add(user)
    url = reverse('archive_browse')
    response = client.get(url)
    assert response.status_code == 200
    q = PyQuery(smart_text(response.content))
    print(elist.name, elist.private, elist.members.all())
    print(user)
    print(type(response.content))
    print(response.content)
    assert len(q('#private-lists li')) == 1


@pytest.mark.django_db(transaction=True)
def test_not_logged_browse_private_list(client, messages):
    '''Test that an unauthenticated user cannot access private list
    browse views
    '''
    message = Message.objects.filter(email_list__name='private').first()
    url = reverse('archive_search') + '?email_list=private&index={}'.format(message.hashcode.strip('='))
    response = client.get(url)
    assert 'No results found' in smart_text(response.content)


@pytest.mark.django_db(transaction=True)
def test_not_logged_search(client, messages):
    '''Test that a not logged in user does not see private lists in search results'''
    url = reverse('archive_search') + '?email_list=private&so=-date'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 0


@pytest.mark.django_db(transaction=True)
def test_not_logged_search_hypen(client, messages):
    '''Test that a not logged in user does not see private lists with hyphen in search results'''
    url = reverse('archive_search') + '?email_list=private-ops&so=-date'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 0


@pytest.mark.django_db(transaction=True)
def test_unauth_search(client, messages):
    """Test that a logged in user does not see results from private lists they aren't a member of"""
    UserFactory.create(username='dummy')
    assert client.login(username='dummy', password='admin')
    url = reverse('archive_search') + '?email_list=private&so=-date'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 0


@pytest.mark.django_db(transaction=True)
def test_console_access(client, admin_client):
    '''Test that only superusers have access to console page'''
    url = reverse('archive_admin_console')
    # anonymous user
    response = client.get(url)
    assert response.status_code == 302
    # admin user
    response = admin_client.get(url)
    assert response.status_code == 200


# --------------------------------------------------
# Keyword Queries
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_queries_from_field(client, messages):
    url = reverse('archive_search') + '?q=from:larry@amsl.com'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 2
    assert 'larry@amsl.com' in getattr(results[0], 'frm')


@pytest.mark.django_db(transaction=True)
def test_queries_subject_field(client, messages):
    url = reverse('archive_search') + '?q=subject:BBQ'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 2
    assert 'BBQ' in results[0].subject


@pytest.mark.django_db(transaction=True)
def test_queries_msgid_field(client, messages):
    msgid = Message.objects.first().msgid
    url = reverse('archive_search') + '?q=msgid:{}'.format(msgid)
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].msgid == msgid


@pytest.mark.django_db(transaction=True)
def test_queries_spam_score_field(client, messages):
    url = reverse('archive_search') + '?q=spam_score:1'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].spam_score == 1


@pytest.mark.django_db(transaction=True)
def test_queries_email_list_field(client, messages):
    url = reverse('archive_search') + '?q=email_list:pubone'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 5
    assert results[0].email_list == 'pubone'


# --------------------------------------------------
# Parameter Queries
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_queries_email_list(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&so=-date'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 5


@pytest.mark.django_db(transaction=True)
def test_queries_email_list_with_hyphen(client, messages):
    url = reverse('archive_search') + '?email_list=dev-ops&so=-date'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1


@pytest.mark.django_db(transaction=True)
def test_queries_email_list_with_bad_name(client, messages):
    url = reverse('archive_search') + '?email_list=dev-ops/'
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_queries_from_param(client, messages):
    url = reverse('archive_search') + '?from=larry@amsl.com'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 2
    assert 'larry@amsl.com' in getattr(results[0], 'frm')


@pytest.mark.django_db(transaction=True)
def test_queries_subject_param(client, messages):
    url = reverse('archive_search') + '?subject=BBQ'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 2
    assert 'BBQ' in results[0].subject


@pytest.mark.django_db(transaction=True)
def test_queries_msgid_param(client, messages):
    msgid = Message.objects.first().msgid
    url = reverse('archive_search') + '?msgid={}'.format(msgid)
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].msgid == msgid


@pytest.mark.django_db(transaction=True)
def test_queries_spam_score_param(client, messages):
    url = reverse('archive_search') + '?spam_score=1'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].spam_score == 1


@pytest.mark.django_db(transaction=True)
def test_queries_gbt_param(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&gbt=1'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 5
    assert [x.msgid for x in results] == ['a02', 'a03', 'a01', 'a04', 'a05']       # assert grouped by thread order


@pytest.mark.django_db(transaction=True)
def test_queries_so_param(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&so=frm'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 5
    assert [x.msgid for x in results] == ['a03', 'a01', 'a02', 'a04', 'a05']


@pytest.mark.django_db(transaction=True)
def test_queries_so_param_subject(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&so=subject'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 5
    print([x.subject_base for x in results])
    assert [x.msgid for x in results] == ['a01', 'a02', 'a04', 'a05', 'a03']


@pytest.mark.django_db(transaction=True)
def test_queries_sso_param(client, messages):
    url = reverse('archive_search') + '?email_list=pubone&so=email_list&sso=frm'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 5
    assert [x.msgid for x in results] == ['a03', 'a01', 'a02', 'a04', 'a05']


# --------------------------------------------------
# Boolean Queries
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_queries_boolean_two_term_implicit(client, messages):
    url = reverse('archive_search') + '?q=invitation+things'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].msgid == 'a04'


@pytest.mark.django_db(transaction=True)
def test_queries_boolean_two_term_and(client, messages):
    url = reverse('archive_search') + '?q=invitation+AND+things'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].msgid == 'a04'


@pytest.mark.django_db(transaction=True)
def test_queries_boolean_two_term_or(client, messages):
    url = reverse('archive_search') + '?q=invitation OR another'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    print(len(results.object_list), results.object_list[0].msgid)
    assert len(results) == 4
    ordered_ids = sorted([r.msgid for r in results])
    assert ordered_ids == ['a01', 'a02', 'a04', 'a05']


@pytest.mark.django_db(transaction=True)
def test_queries_boolean_two_term_grouped(client, messages):
    url = reverse('archive_search') + '?q=(invitation+AND+things)+OR+another'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 2
    assert results[0].msgid in ['a01', 'a04']
    assert results[1].msgid in ['a01', 'a04']


# --------------------------------------------------
# Odd Queries
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_odd_queries(client, messages):
    'Test some odd queries'
    # search with no params
    url = reverse('archive_search')
    response = client.get(url)
    assert response.status_code == 200
    # search with only hyphen
    url = url + '?q=-'
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_queries_bad_qid(client, messages):
    'Test malicious query'
    message = messages.first()
    url = message.get_absolute_url() + "/%3fqid%3ddf6d7ccfedface723ffb184a6f52bab3'+order+by+1+--+;"
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_queries_two_periods(client, messages):
    '''Test that range operator (two periods) doesn't cause error'''
    url = reverse('archive_search') + '?q=spec...)'
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_queries_unicode(client, messages):
    url = reverse('archive_search') + '?q=frm%3ABj%C3%B6rn'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].msgid == 'a01'


# --------------------------------------------------
# Sorted Queries
# --------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_queries_sort_from(client, messages):
    url = reverse('archive_search') + '?email_list=pubthree&so=frm'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert results[0].frm <= results[1].frm


# --------------------------------------------------
# Misc Queries
# --------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_queries_draft(client, messages):
    url = reverse('archive_search') + '?q=draft-ietf-dnssec-secops'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 1
    assert response.context['results'][0].msgid == 'a03'


@pytest.mark.django_db(transaction=True)
def test_queries_draft_partial(client, messages):
    url = reverse('archive_search') + '?q=draft-ietf-dnssec'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 1
    assert response.context['results'][0].msgid == 'a03'


@pytest.mark.django_db(transaction=True)
def test_queries_pagination(client, messages):
    # verify pre-conditions
    message_count = messages.filter(email_list__name='pubthree').count()
    assert message_count == 21
    # test page=2
    url = reverse('archive_search') + '?email_list=pubthree&page=2'
    response = client.get(url)
    print(response.content)
    print(vars(response))
    print('============')
    print(response.context['results'])
    assert response.status_code == 200
    assert len(response.context['results']) == 1


@pytest.mark.django_db(transaction=True)
def test_queries_pagination_bogus(client, messages):
    # verify pre-conditions
    message_count = Message.objects.filter(email_list__name='pubthree').count()
    assert message_count == 21
    # test non integer
    url = reverse('archive_search') + '?email_list=pubthree&page=bogus'
    response = client.get(url)
    assert response.status_code == 404
    # assert len(response.context['results']) == 20   # should get page 1
    # test page too high
    url = reverse('archive_search') + '?email_list=pubthree&page=1000'
    response = client.get(url)
    assert response.status_code == 404
    # assert len(response.context['results']) == 1    # should get last page


@pytest.mark.django_db(transaction=True)
def test_queries_range(client, messages):
    '''Test valid range operator'''
    url = reverse('archive_search') + '?q=date%3A%5B2000-01-01 TO 2013-12-31%5D'
    # url = reverse('archive_search') + '?q=date%3A20000101..20131231'
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context['results']) == 3


@pytest.mark.django_db(transaction=True)
def test_queries_list_term(client):
    '''Test that a single term query that matches a list name redirects to list'''
    EmailListFactory.create(name='pubone')
    url = reverse('archive_search') + '?q=pubone'
    response = client.get(url)
    assert response.status_code == 302
    assert response['location'] == reverse('archive_browse_list', kwargs={'list_name': 'pubone'})


@pytest.mark.django_db(transaction=True)
def test_queries_draft_name(client, messages):
    url = reverse('archive_search') + '?q=draft-ietf-dnssec-secops'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert 'draft-ietf-dnssec-secops' in results[0].subject


# --------------------------------------------------
# Elastic Specific Tests
# --------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_queries_boolean_negated_term(client, messages):
    url = reverse('archive_search') + '?q=-rfc6759'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) > 1
    assert 'a01' not in [x.msgid for x in results]


@pytest.mark.django_db(transaction=True)
def test_queries_boolean_wildcard(client, messages):
    url = reverse('archive_search') + '?q=*6759'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']
    assert len(results) == 1
    assert results[0].msgid == 'a01'


'''
@pytest.mark.django_db(transaction=True)
def test_queries_partial_match(client,messages):
    """For example search for 6759 should match RFC6759"""
    url = reverse('archive_search') + '?q=6759'
    response = client.get(url)
    assert response.status_code == 200
    results = response.context['results']

    msg = Message.objects.get(msgid='a01')
    print msg.subject, msg.base_subject
    assert len(results) == 1
    assert 'RFC6759' in results[0].subject
'''
