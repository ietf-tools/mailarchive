from mlarchive.archive.forms import AdvancedSearchForm

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

import time
import urllib

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

FILTER_PARAMS = ['f_list','f_from', 'so', 'sso', 'page']

def has_filters(request):
    '''
    Returns True if the request URL contains search filters.
    NOTE: function will return false if filters exist but with no value.  ie.  "f_List="
    '''
    for filter in FILTER_PARAMS:
        if request.GET.get(filter):
            return True
    return False

"""
def get_base_query(querydict):
    '''
    Takes a QueryDict object, strips any filter parameters (FILTER_PARAMS) and returns
    the resulting base query string.  For use with calculating base facets.
    '''
    qd_copy = querydict.copy()      # can't modify original query dict
    for filter in FILTER_PARAMS:
        if filter in qd_copy:
            del qd_copy[filter]
    return qd_copy.urlencode()
"""

def get_base_query(querydict):
    '''
    Takes a QueryDict object, strips any filter parameters (FILTER_PARAMS) and returns
    the resulting base query string.  For use with calculating base facets.
    '''
    d = dict((k,v) for k,v in querydict.iteritems() if k not in FILTER_PARAMS)
    return urllib.urlencode(d)

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
        # just return if this isn't a search without filters
        if not request.get_full_path().startswith('/archive/search/'):
            return None

        logger.info('QueryMiddleware:process_request() %s' % request.META['QUERY_STRING'])

        # init session dict
        if 'queries' not in request.session:
            request.session['queries'] = {}

        # - if the base query isn't already stored, get facets and store
        # assert False, request.GET
        query = get_base_query(request.GET)
        if query not in request.session['queries']:
            # call search function from here
            data = request.GET
            form = AdvancedSearchForm(data,load_all=False,request=request)
            results = form.search()
            # calculating facet_counts on large results sets is too costly so skip it
            # TODO: this might also be implemented as a timeout
            #
            # If you call results.count() before results.facet_counts() the facet_counts
            # are corrupted.  The solution is to clone the query and call counts on that
            temp = results._clone()
            if temp.count() < 15000:
                base_facets = results.facet_counts()
                #assert False, (results,query,base_facets)
                for field in base_facets['fields']:
                    # need to set a hard limit, can't disaply unlimited number of options
                    # logger.info('facets count for %s:%s' % (field,len(base_facets['fields'][field])))
                    #if len(base_facets['fields'][field]) > 30:
                        # get the top thirty sorted by facet count
                    #    sorted_facets = sorted(base_facets['fields'][field], key=lambda k: k[1],reverse=True)
                    #    base_facets['fields'][field] = sorted_facets[:30]
                    base_facets['fields'][field].sort()  # sort by name
            else:
                base_facets = None
            request.session['queries'][query] = base_facets
            request.session.save()      # don't know why this is required but it is
            logger.info('middleware: %s' % request.session['queries'].keys())
            logger.info('middleware: %s' % request.session.session_key)

        return None