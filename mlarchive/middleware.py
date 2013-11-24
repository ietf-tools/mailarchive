from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.models import EmailList

from django.conf import settings
from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

import time
import urllib

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

EXTRA_PARAMS = ('so', 'sso', 'page', 'gbt')
ALL_PARAMS = ('f_list','f_from', 'so', 'sso', 'page', 'gbt')

def get_base_query(querydict,filters=False,string=False):
    '''
    Get the base query by stripping any extra parameters from the query.
    Expects a QueryDict object, ie. request.GET.  Returns a copy of the querydict
    with parameters removed, or the query as a string if string=True.  Optional boolean
    "filters".  If filters=True leave filter parameters intact. For use with calculating
    base facets.

    NOTE: the base query string we are using as a key is urlencoded.  Another option is to save
    the query unquoted using urlib.unquote_plus()
    '''
    if filters:
        params = EXTRA_PARAMS
    else:
        params = ALL_PARAMS
    copy = querydict.copy()
    for key in querydict:
        if key in params:
            copy.pop(key)
    if string:
        return copy.urlencode()
    else:
        return copy

def has_extras(request):
    '''
    Returns True if the request URL contains extra search parameters (filters, sort, paging)
    NOTE: function will return false if parameters exist but with no value.  ie.  "f_List="
    '''
    for param in EXTRA_PARAMS:
        if request.GET.get(param):
            return True
    return False

def log_timing(func):
    '''
    This is a decorator that logs the time it took to complete the decorated function.
    Handy for performance testing
    '''
    def wrapper(*arg):
        t1 = time.time()
        res = func(*arg)
        t2 = time.time()
        logger.info('%s took %0.3f ms' % (func.func_name, (t2-t1)*1000.0))
        return res
    return wrapper

# --------------------------------------------------
# Middleware Classes
# --------------------------------------------------
