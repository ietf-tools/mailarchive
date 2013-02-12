from mlarchive.archive.forms import AdvancedSearchForm

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

import time

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

class QueryMiddleware(object):
    '''
    Check the submitted query, if it is an original query, in other words not a secondary
    filter query, as indicated by the lack of "selected_items", save the base facet counts
    in the session.  We have to do this in order to retain the full set of facet counts.  Once
    a user selects a facet for filtering the original base set is no longer available in the
    query response.  session['base_facets'] will be used in a context processor.
    '''
    #@log_timing
    def process_request(self, request):
        logger.info('QueryMiddleware:process_request() %s' % request.META['QUERY_STRING'])
        if request.META['REQUEST_URI'].startswith('/archive/search/'):
            if not request.GET.get('f_list'):
                # init session dict
                if 'queries' not in request.session:
                    request.session['queries'] = {}
                # if the query isn't already stored, get facets and store
                if request.META['QUERY_STRING'] not in request.session['queries']:
                    # call search function from here
                    data = request.GET
                    form = AdvancedSearchForm(data,load_all=False,request=request)
                    results = form.search()
                    # calculating facet_counts on large results sets is too costly so skip it
                    # TODO: this might also be implemented as a timeout
                    # If you call results.count() before results.facet_counts() the facet_counts
                    # are corrupted.  The solution is to clone the query and call counts on that
                    temp = results._clone()
                    if temp.count() < 15000:
                        base_facets = results.facet_counts()
                        for field in base_facets['fields']:
                            base_facets['fields'][field].sort()  # sort by name
                    else:
                        base_facets = None
                    request.session['queries'][request.META['QUERY_STRING']] = base_facets
                    request.session.save()      # don't know why this is required but it is
                    logger.info('middleware: %s' % request.session['queries'].keys())
                    logger.info('middleware: %s' % request.session.session_key)
        return None