import random
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from haystack.query import SQ

from mlarchive.archive.utils import get_lists

import logging
logger = logging.getLogger('mlarchive.custom')

VALID_QUERYID_RE = re.compile(r'^[a-f0-9]{32}$')
FILTER_PARAMS = ('f_list','f_from')
NON_FILTER_PARAMS = ('so', 'sso', 'page', 'gbt')

# --------------------------------------------------
# Functions handle URL parameters
# --------------------------------------------------
def clean_queryid(query_id):
    if VALID_QUERYID_RE.match(query_id):
        return query_id
    else:
        return None

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
    if 'qid' in request.GET:
        queryid = clean_queryid(request.GET['qid'])
        if queryid:
            return (queryid, cache.get(queryid))
    return (None, None)

def get_filter_params(query):
    """Return list of filter parameters that appear in the query"""
    return [ k for k,v in query.items() if k in FILTER_PARAMS and v ]

def get_kwargs(data):
    """Returns a dictionary to be used as kwargs for the SearchQuerySet, data is
    a dictionary from form.cleaned_data.  This function can be used with multiple
    forms which may not include exactly the same fields, so we use the get() method.
    """
    kwargs = {}
    spam_score = data.get('spam_score')
    for key in ('msgid',):
        if data.get(key):
            kwargs[key] = data[key]
    if data.get('start_date'):
        kwargs['date__gte'] = data['start_date']
    if data.get('end_date'):
        kwargs['date__lte'] = data['end_date']
    if data.get('email_list'):
        # with Haystack/Xapian must replace dash with space in email list names
        kwargs['email_list__in'] = [ x.replace('-',' ') for x in data['email_list'] ]
    if data.get('frm'):
        kwargs['frm__icontains'] = data['frm']
    if data.get('qdr') and data['qdr'] not in ('a','c'):
        kwargs['date__gte'] = get_qdr_time(data['qdr'])
    if data.get('subject'):
        kwargs['subject__icontains'] = data['subject']
    if data.get('spam'):
        kwargs['spam_score__gt'] = 0
    if spam_score and spam_score.isdigit():
        bits = [ x for x in range(255) if x & int(spam_score)]
        kwargs['spam_score__in'] = bits
    return kwargs

def get_qdr_time(val):
    """Expects the value of the qdr search parameter [h,d,w,m,y]
    and returns the corresponding datetime to use in the search filter.
    EXAMPLE: h -> now - one hour
    """
    now = datetime.now()
    if val == 'h':
        return now - timedelta(hours=1)
    elif val == 'd':
        return now - timedelta(days=1)
    elif val == 'w':
        return now - timedelta(weeks=1)
    elif val == 'm':
        return now - timedelta(days=30)
    elif val == 'y':
        return now - timedelta(days=365)

def get_query(request):
    """Returns the query as a string.  Usually this is just the 'q' parameter.
    However, in the case of an advanced search with javascript disabled we need
    to build the query given the query parameters in the request"""
    if request.GET.get('q'):
        return request.GET.get('q')
    elif 'nojs' in request.META['QUERY_STRING']:
        query = []
        not_query = []
        items = filter(is_nojs_value, request.GET.items())
        for key,value in items:
            field = request.GET[key.replace('value','field')]
            qualifier = request.GET[key.replace('value','qualifier')]
            if 'query' in key:
                query.append('{}:({})'.format(field,value))
            else:
                not_query.append('-{}:({})'.format(field,value))
        return ' '.join(query + not_query)
    else:
        return ''

def is_nojs_value(items):
    k,v = items
    if k.startswith('nojs') and k.endswith('value') and v:
        return True
    else:
        return False

def query_is_listname(request):
    query = request.GET.get('q', '')
    if request.GET.keys() == ['q'] and len(query.split()) == 1 and query in get_lists():
        return True
    else:
        return False