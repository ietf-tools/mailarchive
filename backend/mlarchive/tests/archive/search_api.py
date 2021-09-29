import pytest
from urllib.parse import urlencode

from django.contrib.auth.models import AnonymousUser
from django.http import QueryDict

from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.backends.elasticsearch import search_from_form

# --------------------------------------------------
# Low level form.search() tests
# --------------------------------------------------


def test_ensure_index(settings):
    assert settings.ELASTICSEARCH_INDEX_NAME == 'test-mail-archive'


# ------------------------------
# Boolean Operators
# ------------------------------
@pytest.mark.django_db(transaction=True)
def test_form_one_term(rf, client, search_api_messages):
    '''One term'''
    request = rf.get('/arch/search/?q=bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    print(search.to_dict())
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_two_term(rf, client, search_api_messages):
    '''Two terms, implied AND'''
    request = rf.get('/arch/search/?q=apples+bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=apples+bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003']


@pytest.mark.django_db(transaction=True)
def test_form_two_term_and(rf, client, search_api_messages):
    '''Two terms, explicit AND'''
    request = rf.get('/arch/search/?q=apples+AND+bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=apples+AND+bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003']


@pytest.mark.django_db(transaction=True)
def test_form_two_term_or(rf, client, search_api_messages):
    '''Two terms, explicit OR'''
    request = rf.get('/arch/search/?q=apples+OR+bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=apples+OR+bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 3
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_one_term_not(rf, client, search_api_messages):
    '''One term, NOT'''
    request = rf.get('/arch/search/?q=NOT+bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=NOT+bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api004']


@pytest.mark.django_db(transaction=True)
def test_form_one_term_negate(rf, client, search_api_messages):
    '''One term, NOT with minus sign'''
    request = rf.get('/arch/search/?q=-bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=-bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api004']


@pytest.mark.django_db(transaction=True)
def test_form_parens(rf, client, search_api_messages):
    '''Parenthesis'''
    request = rf.get('/arch/search/?q=(bananas+AND+apples)+OR+oranges')
    request.user = AnonymousUser()
    data = QueryDict('q=(bananas+AND+apples)+OR+oranges')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003', 'api004']


# ------------------------------------------------------
# URL params (qdr, start_date, end_date, msgid, subject)
# ------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_form_params_start_date(rf, client, search_api_messages):
    '''Test params: start_date'''
    data = QueryDict('start_date=2020-02-15')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003', 'api004']


@pytest.mark.django_db(transaction=True)
def test_form_params_end_date(rf, client, search_api_messages):
    data = QueryDict('end_date=2020-02-15')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002']


@pytest.mark.django_db(transaction=True)
def test_form_params_msgid(rf, client, search_api_messages):
    data = QueryDict('msgid=api001')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001']


@pytest.mark.django_db(transaction=True)
def test_form_params_email_list(rf, client, search_api_messages, search_api_messages_ford):
    # search acme list
    data = QueryDict('email_list=acme')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003', 'api004']
    # search ford list
    data = QueryDict('email_list=ford')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api201', 'api202', 'api203', 'api204']


@pytest.mark.django_db(transaction=True)
def test_form_params_email_list_multi(rf, client, search_api_messages, search_api_messages_ford):
    # search two lists - text input
    data = QueryDict('email_list=acme&email_list=ford')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 8
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003', 'api004', 'api201', 'api202', 'api203', 'api204']
    # search two lists - multi-select input
    data = QueryDict('email_list=acme+ford')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 8
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003', 'api004', 'api201', 'api202', 'api203', 'api204']


@pytest.mark.django_db(transaction=True)
def test_form_params_from(rf, client, search_api_messages):
    data = QueryDict('frm=Bilbo')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003']


@pytest.mark.django_db(transaction=True)
def test_form_params_subject(rf, client, search_api_messages):
    data = QueryDict('subject=apples')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_params_qdr(rf, client, search_api_messages_qdr):
    data = QueryDict('qdr=d')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301']
    # test week
    data = QueryDict('qdr=w')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301', 'api302']
    # test month
    data = QueryDict('qdr=m')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 3
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301', 'api302', 'api303']
    # test year
    data = QueryDict('qdr=y')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301', 'api302', 'api303', 'api304']

# ------------------------------
# Private lists
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_form_private_no_access(rf, client, search_api_messages, private_messages):
    '''Public request, no access'''
    request = rf.get('/arch/search/?q=bananas')
    request.user = AnonymousUser()
    data = QueryDict('q=bananas')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_private_logged_in_no_access(rf, client, search_api_messages, private_messages):
    '''Logged in, no access'''
    pass


@pytest.mark.django_db(transaction=True)
def test_form_private_logged_in_access(rf, client, search_api_messages, private_messages):
    '''Logged in with access'''
    pass

# ------------------------------
# Filtering
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_form_filter_list(rf, client, search_api_messages, search_api_messages_ford):
    '''Test list filter'''
    # no filter
    request = rf.get('/arch/search/?q=test')
    request.user = AnonymousUser()
    data = QueryDict('q=test')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 8
    # list filter
    data = QueryDict('q=test&f_list=ford')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api201', 'api202', 'api203', 'api204']


@pytest.mark.django_db(transaction=True)
def test_form_filter_from(rf, client, search_api_messages):
    '''Test from filter'''
    # no filter
    request = rf.get('/arch/search/?q=test')
    request.user = AnonymousUser()
    data = QueryDict('q=test')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    # from filter
    data = QueryDict('q=test&f_from=Holden+Ford')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    print(search.to_dict())
    results = search.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002']


# ------------------------------
# Ordering
# ------------------------------

@pytest.mark.django_db(transaction=True)
def test_form_sort_from(rf, client, search_api_messages):
    '''Test sort by From field'''
    request = rf.get('/arch/search/?q=test&so=frm')
    request.user = AnonymousUser()
    data = QueryDict('q=test&so=frm')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert ids == ['api003', 'api002', 'api004', 'api001']

# ------------------------------
# Facets
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_form_aggs(rf, client, search_api_messages, search_api_messages_ford):
    '''Aggregates. No filter'''
    request = rf.get('/arch/search/?q=test')
    request.user = AnonymousUser()
    data = QueryDict('q=test')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 8
    assert hasattr(results, 'aggregations')
    assert results.aggregations.list_terms.buckets == [
        {'key': 'acme', 'doc_count': 4},
        {'key': 'ford', 'doc_count': 4}]
    fbuckets = results.aggregations.from_terms.buckets
    sfbuckets = sorted(fbuckets, key=lambda x: x['key'])
    assert sfbuckets == [
        {'key': 'Bilbo Baggins', 'doc_count': 1},
        {'key': 'Holden Ford', 'doc_count': 2},
        {'key': 'Huxley Ford', 'doc_count': 1},
        {'key': 'User', 'doc_count': 3},
        {'key': 'Zaphod Beeblebrox', 'doc_count': 1}]


@pytest.mark.django_db(transaction=True)
def test_form_aggs_list_filter(rf, client, search_api_messages, search_api_messages_ford):
    '''Aggregates. List filter'''
    request = rf.get('/arch/search/?q=test&f_list=acme')
    request.user = AnonymousUser()
    data = QueryDict('q=test&f_list=acme')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 4
    assert hasattr(results, 'aggregations')
    assert results.aggregations.list_terms.buckets == [{'key': 'acme', 'doc_count': 4}]
    fbuckets = results.aggregations.from_terms.buckets
    sfbuckets = sorted(fbuckets, key=lambda x: x['key'])
    assert sfbuckets == [
        {'key': 'Bilbo Baggins', 'doc_count': 1},
        {'key': 'Holden Ford', 'doc_count': 1},
        {'key': 'Huxley Ford', 'doc_count': 1},
        {'key': 'Zaphod Beeblebrox', 'doc_count': 1}]


@pytest.mark.django_db(transaction=True)
def test_form_aggs_from_filter(rf, client, search_api_messages, search_api_messages_ford):
    '''Aggregates. From filter'''
    request = rf.get('/arch/search/?q=test&f_from=Holden+Ford')
    request.user = AnonymousUser()
    data = QueryDict('q=test&f_from=Holden+Ford')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    assert hasattr(results, 'aggregations')
    assert results.aggregations.list_terms.buckets == [
        {'key': 'acme', 'doc_count': 1},
        {'key': 'ford', 'doc_count': 1}]
    assert results.aggregations.from_terms.buckets == [
        {'key': 'Holden Ford', 'doc_count': 2}]


@pytest.mark.django_db(transaction=True)
def test_form_aggs_both_filters(rf, client, search_api_messages, search_api_messages_ford):
    '''Aggregates. List and From filters'''
    request = rf.get('/arch/search/?q=test&f_list=acme&f_from=Holden+Ford')
    request.user = AnonymousUser()
    data = QueryDict('q=test&f_from=Holden+Ford&f_list=acme')
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 1
    assert hasattr(results, 'aggregations')
    assert results.aggregations.list_terms.buckets == [{'key': 'acme', 'doc_count': 1}]
    assert results.aggregations.from_terms.buckets == [
        {'key': 'Holden Ford', 'doc_count': 1}]


# ------------------------------
# Field searches
# ------------------------------

@pytest.mark.django_db(transaction=True)
def test_form_fields_subject(rf, client, search_api_messages):
    data = QueryDict('q=subject:apples')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_fields_frm(rf, client, search_api_messages):
    data = QueryDict('q=from:Ford')
    request = rf.get('/arch/search/?' + data.urlencode())
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    search = search_from_form(form)
    results = search.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api004']
