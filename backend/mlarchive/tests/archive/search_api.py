import pytest
from urllib.parse import urlencode

from django.contrib.auth.models import AnonymousUser

from mlarchive.archive.forms import AdvancedSearchForm

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
    data = {'q': 'bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    print(query.to_dict())
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_two_term(rf, client, search_api_messages):
    '''Two terms, implied AND'''
    request = rf.get('/arch/search/?q=apples+bananas')
    request.user = AnonymousUser()
    data = {'q': 'apples+bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003']


@pytest.mark.django_db(transaction=True)
def test_form_two_term_and(rf, client, search_api_messages):
    '''Two terms, explicit AND'''
    request = rf.get('/arch/search/?q=apples+AND+bananas')
    request.user = AnonymousUser()
    data = {'q': 'apples+AND+bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003']


@pytest.mark.django_db(transaction=True)
def test_form_two_term_or(rf, client, search_api_messages):
    '''Two terms, explicit OR'''
    request = rf.get('/arch/search/?q=apples+OR+bananas')
    request.user = AnonymousUser()
    data = {'q': 'apples+OR+bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 3
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_one_term_not(rf, client, search_api_messages):
    '''One term, NOT'''
    request = rf.get('/arch/search/?q=NOT+bananas')
    request.user = AnonymousUser()
    data = {'q': 'NOT+bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api004']


@pytest.mark.django_db(transaction=True)
def test_form_one_term_negate(rf, client, search_api_messages):
    '''One term, NOT'''
    request = rf.get('/arch/search/?q=-bananas')
    request.user = AnonymousUser()
    data = {'q': '-bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api004']


@pytest.mark.django_db(transaction=True)
def test_form_parens(rf, client, search_api_messages):
    '''One term, NOT'''
    request = rf.get('/arch/search/?q=(bananas+AND+apples)+OR+oranges')
    request.user = AnonymousUser()
    data = {'q': '(bananas+AND+apples)+OR+oranges'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003', 'api004']


# ------------------------------------------------------
# URL params (qdr, start_date, end_date, msgid, subject)
# ------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_form_params_start_date(rf, client, search_api_messages):
    '''Test params: start_date'''
    data = {'start_date': '2020-02-15'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003', 'api004']


@pytest.mark.django_db(transaction=True)
def test_form_params_end_date(rf, client, search_api_messages):
    data = {'end_date': '2020-02-15'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002']


@pytest.mark.django_db(transaction=True)
def test_form_params_msgid(rf, client, search_api_messages):
    data = {'msgid': 'api001'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001']


@pytest.mark.django_db(transaction=True)
def test_form_params_email_list(rf, client, search_api_messages, search_api_messages_ford):
    # search acme list
    data = {'email_list': ['acme']}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api001', 'api002', 'api003', 'api004']
    # search ford list
    data = {'email_list': ['ford']}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api201', 'api202', 'api203', 'api204']


@pytest.mark.django_db(transaction=True)
def test_form_params_from(rf, client, search_api_messages):
    data = {'frm': 'Bilbo'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api003']


@pytest.mark.django_db(transaction=True)
def test_form_params_subject(rf, client, search_api_messages):
    data = {'subject': 'apples'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_params_qdr(rf, client, search_api_messages_qdr):
    data = {'qdr': 'd'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 1
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301']
    # test week
    data = {'qdr': 'w'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301', 'api302']
    # test month
    data = {'qdr': 'm'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 3
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api301', 'api302', 'api303']
    # test year
    data = {'qdr': 'y'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
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
    data = {'q': 'bananas'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
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
    data = {'q': 'test'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 8
    # list filter
    data = {'q': 'test', 'f_list': 'ford'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api201', 'api202', 'api203', 'api204']


@pytest.mark.django_db(transaction=True)
def test_form_filter_from(rf, client, search_api_messages):
    '''Test from filter'''
    # no filter
    request = rf.get('/arch/search/?q=test')
    request.user = AnonymousUser()
    data = {'q': 'test'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 4
    # from filter
    data = {'q': 'test', 'f_from': 'Holden Ford'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api004']


# ------------------------------
# Ordering
# ------------------------------

@pytest.mark.django_db(transaction=True)
def test_form_sort_from(rf, client, search_api_messages):
    '''Test sort by From field'''
    request = rf.get('/arch/search/?q=test&so=frm')
    request.user = AnonymousUser()
    data = {'q': 'test', 'so': 'frm'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 4
    ids = [h.msgid for h in results]
    assert ids == ['api003', 'api002', 'api004', 'api001']

# ------------------------------
# Facets
# ------------------------------


@pytest.mark.django_db(transaction=True)
def test_form_aggs(rf, client, search_api_messages):
    '''One term'''
    request = rf.get('/arch/search/?q=test')
    request.user = AnonymousUser()
    data = {'q': 'test'}
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 4
    assert hasattr(results, 'aggregations')
    assert results.aggregations.list_terms.buckets == [{'key': 'acme', 'doc_count': 4}]
    assert results.aggregations.from_terms.buckets == [
        {'key': 'Holden Ford', 'doc_count': 2},
        {'key': 'Bilbo Baggins', 'doc_count': 1},
        {'key': 'Zaphod Beeblebrox', 'doc_count': 1}]


@pytest.mark.django_db(transaction=True)
def test_form_aggs_list_filter(rf, client, search_api_messages):
    pass


@pytest.mark.django_db(transaction=True)
def test_form_aggs_from_filter(rf, client, search_api_messages):
    pass


@pytest.mark.django_db(transaction=True)
def test_form_aggs_both_filters(rf, client, search_api_messages):
    pass


# ------------------------------
# Field searches
# ------------------------------

@pytest.mark.django_db(transaction=True)
def test_form_fields_subject(rf, client, search_api_messages):
    data = {'q': 'subject:apples'}
    request = rf.get('/arch/search/?' + urlencode(data))
    request.user = AnonymousUser()
    form = AdvancedSearchForm(data=data, request=request)
    query = form.search()
    results = query.execute()
    assert len(results) == 2
    ids = [h.msgid for h in results]
    assert sorted(ids) == ['api002', 'api003']


@pytest.mark.django_db(transaction=True)
def test_form_fields_frm(rf, client, search_api_messages):
    assert False