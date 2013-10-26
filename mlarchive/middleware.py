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

class QueryMiddleware(object):
    '''
    Get the base query (strip filters and sorts).  Get facet counts for base query if they
    aren't already cached in the Session.  We have to do this in order to retain the full set
    of facet counts.  Once a user selects a facet for filtering the original base set is no
    longer available in the query response.  session['base_facets'] will be used in a context
    processor.

    NOTE: the base query string we are using as a key is urlencoded.  Another option is to save
    the query unquoted using urlib.unquote_plus()
    '''
    #@log_timing
    def process_request(self, request):
        if not request.get_full_path().startswith('/archive/search/'):
            return None

        logger.info('QueryMiddleware:process_request() %s' % request.META['QUERY_STRING'])
        if 'queries' not in request.session:
            request.session['queries'] = {}

        # leave filter options in facet cache key because counts will be unqiue
        query = get_base_query(request.GET,filters=True,string=True)
        if query not in request.session['queries']:
            # strip sorts and filters and run base query
            data = get_base_query(request.GET,filters=False,string=False)
            form = AdvancedSearchForm(data,load_all=False,request=request)
            results = form.search()

            # calculating facet_counts on large results sets is too costly so skip it
            # If you call results.count() before results.facet_counts() the facet_counts
            # are corrupted.  The solution is to clone the query and call counts on that
            # TODO: this might also be implemented as a timeout
            temp = results._clone()
            count = temp.count()
            if count == 0:
                return None
            if count < settings.FILTER_CUTOFF:
                base_facets = results.facet_counts()

                # convert email list IDs to names
                # TODO: cache this table
                new = [ (EmailList.objects.get(id=x).name,y) for x,y in base_facets['fields']['email_list'] ]
                base_facets['fields']['email_list'] = new
                for field in base_facets['fields']:
                    base_facets['fields'][field].sort()  # sort by name
            else:
                base_facets = None
            request.session['queries'][query] = base_facets
            request.session.save()          # don't know why this is required but it is
            logger.info('middleware: %s' % request.session['queries'].keys())
            # logger.info('middleware: %s' % request.session.session_key)

        return None