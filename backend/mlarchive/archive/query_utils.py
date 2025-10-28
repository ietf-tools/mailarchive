import datetime
import random
import re

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import RequestError
from elasticsearch_dsl import Q, Search

from mlarchive.archive.utils import get_lists

import logging
logger = logging.getLogger(__name__)


VALID_QUERYID_RE = re.compile(r'^[a-f0-9]{32}$')
FILTER_PARAMS = ('f_list', 'f_from')
NON_FILTER_PARAMS = ('so', 'sso', 'page', 'gbt')

VALID_SORT_OPTIONS = ('frm', '-frm', 'date', '-date', 'email_list', '-email_list',
                      'subject', '-subject')

DEFAULT_SORT = getattr(settings, 'ARCHIVE_DEFAULT_SORT', '-date')
DB_THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
IDX_THREAD_SORT_FIELDS = ('-thread_date', 'thread_id', 'thread_order')


# --------------------------------------------------
# Functions handle URL parameters
# --------------------------------------------------


def generate_queryid():
    return '%032x' % random.getrandbits(128)


def get_base_query(querydict):
    """Expects a QueryDict object, ie. request.GET.  Returns a copy of the querydict
    with sorting or grouping parameters (those which do not alter the content of
    the results) removed.
    """
    copy = querydict.copy()
    for key in querydict:
        if key in NON_FILTER_PARAMS:
            copy.pop(key)
    return copy


def get_cached_query(request):
    queryid = request.GET.get('qid')
    if queryid:
        queryid = clean_queryid(queryid)
    if not queryid:
        return (None, None)

    logger.debug('Looking up queryid: {}'.format(queryid))
    search_dict = cache.get(queryid)
    if search_dict:
        logger.debug('Found search in cache: {}'.format(search_dict))
        connection_options = settings.ELASTICSEARCH_CONNECTION
        client = Elasticsearch(
            connection_options['URL'],
            index=connection_options['INDEX_NAME'],
            http_auth=connection_options['http_auth'],
            **connection_options.get('KWARGS', {}))
        search = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
        search = search.update_from_dict(search_dict)
        logger.debug('Built search object from cache: {}'.format(search))
        return (queryid, search)
    else:
        return (None, None)


def clean_queryid(query_id):
    if VALID_QUERYID_RE.match(query_id):
        return query_id
    else:
        return None


def get_filter_params(query):
    """Return list of filter parameters that appear in the query"""
    return [k for k, v in list(query.items()) if k in FILTER_PARAMS and v]


def filters_from_params(params):
    """Returns a list of filters (filter context) built from parameters"""
    filters = []
    if params.get('f_list'):
        filters.append(Q('terms', email_list=params['f_list']))
    if params.get('f_from'):
        filters.append(Q('terms', frm_name=params['f_from']))
    if params.get('msgid'):
        filters.append(Q('term', msgid=params['msgid']))
    if params.get('start_date'):
        filters.append(Q('range', date={'gte': params['start_date']}))
    if params.get('end_date'):
        filters.append(Q('range', date={'lte': params['end_date']}))
    if params.get('email_list'):
        filters.append(Q('terms', email_list=params['email_list']))
    if params.get('qdr') and params.get('qdr') in ['d', 'w', 'm', 'y']:
        filters.append(Q('range', date={'gte': get_qdr_time_iso(params['qdr'])}))
    # used in admin
    if params.get('spam_score'):
        filters.append(Q('term', spam_score=params['spam_score']))
    if params.get('exclude_not_spam'):
        filters.append(~Q('term', spam_score=settings.SPAM_SCORE_NOT_SPAM))
    return filters


def queries_from_params(params):
    queries = []
    if params.get('frm'):
        queries.append(Q('match', frm=params['frm']))
    if params.get('subject'):
        queries.append(Q('match', subject=params['subject']))
    logger.debug('queries_from_params: {}, params: {}'.format(queries, params))
    return queries


def get_qdr_kwargs(data):
    qdr_kwargs = {}
    if data.get('qdr') and data['qdr'] in ('d', 'w', 'm', 'y'):
        qdr_kwargs['date__gte'] = get_qdr_time(data['qdr'])

    return qdr_kwargs


def get_qdr_time(val):
    """Expects the value of the qdr search parameter [h,d,w,m,y]
    and returns the corresponding datetime to use in the search filter.
    EXAMPLE: h -> now - one hour
    """
    now = datetime.datetime.now(datetime.UTC)
    if val == 'h':
        return now - datetime.timedelta(hours=1)
    elif val == 'd':
        return now - datetime.timedelta(days=1)
    elif val == 'w':
        return now - datetime.timedelta(weeks=1)
    elif val == 'm':
        return now - datetime.timedelta(days=30)
    elif val == 'y':
        return now - datetime.timedelta(days=365)


def get_qdr_time_iso(val):
    """QDR time in ISO 8601 format"""
    return get_qdr_time(val).isoformat()


def get_order_fields(params, use_db=False):
    """Returns the list of fields to use in queryset ordering.
    use_db: use database sort fields, as opposed to index sort fields
    TODO: synchronize index and database sort fields
    """
    if params.get('gbt'):
        if use_db:
            return DB_THREAD_SORT_FIELDS
        else:
            return IDX_THREAD_SORT_FIELDS

    # default sort order is date descending
    so = map_sort_option(params.get('so', DEFAULT_SORT), use_db)
    sso = map_sort_option(params.get('sso'), use_db)
    fields = [v for v in (so, sso) if v]
    return fields if fields else [DEFAULT_SORT]


def map_sort_option(val, use_db=False):
    """This function takes a sort parameter and validates and maps it for use
    in an order_by clause.
    TODO: do in a dictionary instead
    """
    if val not in VALID_SORT_OPTIONS:
        return ''
    if val in ('frm', '-frm') and not use_db:
        val = val + '_name'
    if val == 'subject':
        val = 'base_subject'
    if val == '-subject':
        val = '-base_subject'
    return val


def parse_query(request):
    """Returns the query as a string.  Usually this is just the 'q' parameter.
    However, in the case of an advanced search with javascript disabled we need
    to build the query given the query parameters in the request"""
    if request.GET.get('q'):
        return parse_query_string(request.GET.get('q'))
    elif 'nojs' in request.META['QUERY_STRING']:
        query = []
        not_query = []
        items = list(filter(is_nojs_value, list(request.GET.items())))
        for key, value in items:
            field = request.GET[key.replace('value', 'field')]
            # qualifier = request.GET[key.replace('value','qualifier')]
            if 'query' in key:
                query.append('{}:({})'.format(field, value))
            else:
                not_query.append('-{}:({})'.format(field, value))
        return ' '.join(query + not_query)
    else:
        return ''


def parse_query_string(query):
    # Map from => frm
    if 'from:' in query:
        query = query.replace('from:', 'frm:')
    return query


def is_nojs_value(items):
    k, v = items
    if k.startswith('nojs') and k.endswith('value') and v:
        return True
    else:
        return False


def get_browse_equivalent(request):
    """Returns the listname if the query params are the equivalent of a list browse:
    /?q=[listname] or /?email_list=[listname]"""
    if list(request.GET) == ['q'] and request.GET.get('q') in get_lists():
        return request.GET.get('q')
    if list(request.GET) == ['email_list'] and len(request.GET.getlist('email_list')) == 1:
        return request.GET.get('email_list')


def is_static_on(request):
    return True if request.COOKIES.get('isStaticOn') == 'true' else False


def run_query(query):
    '''Wrapper to execute the query, handling exceptions'''
    # if 'size' not in query._extra:
    #     query = query.extra(size=settings.SEARCH_RESULTS_PER_PAGE)
    try:
        response = query.execute()
    except RequestError:
        '''Could get this when query_string can't parse the query string,
        when there is a bogus search query for example. Swap out query
        with one that returns empty results'''
        query = query.update_from_dict({'query': {'term': {'dummy': ''}}})
        response = query.execute()
    return response


def get_count(query):
    '''Wrapper to run count(), handling query exceptions'''
    if isinstance(query, list):
        return len(query)
    try:
        count = query.count()
    except RequestError:
        '''Could get this when query_string can't parse the query string,
        when there is a bogus search query for example. Swap out query
        with one that returns empty results'''
        query = query.update_from_dict({'query': {'term': {'dummy': ''}}})
        count = query.count()
    return count


# TODO: remove?
def get_empty_response():
    '''Return an empty elasticsearch response'''
    connection_options = settings.ELASTICSEARCH_CONNECTION
    client = Elasticsearch(
        connection_options['URL'],
        index=connection_options['INDEX_NAME'],
        http_auth=connection_options['http_auth'],
        **connection_options.get('KWARGS', {}))
    s = Search(using=client, index=settings.ELASTICSEARCH_INDEX_NAME)
    s = s.query('term', dummy='')
    return s.execute()


class CustomPaginator(Paginator):
    '''A Django Paginator customized to handle Elasticsearch Search
    object as object_list input. page.object_list is the search
    response object'''

    def page(self, number):
        """Return a Page object for the given 1-based page number."""
        # Note: this will call search.count() which will unveil
        # any parsing errors
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        # add slice info to query and execute to get actual object_list
        query = self.object_list[bottom:top]
        if hasattr(query, 'execute'):
            response = run_query(query)
        else:
            response = query

        return self._get_page(response, number, self)
