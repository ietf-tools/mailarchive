from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

class QueryMiddleware(object):
    '''
    Check the submitted query, if it is an original query, in other words not a secondary
    filter query, as indicated by the lack of "selected_items", save the base facet counts
    in the session.  We have to do this in order to retain the full set of facet counts.  Once
    a user selects a facet for filtering the original base set is no longer available in the
    query response.  session['base_facets'] will be used in a context processor.
    '''
    def process_request(self, request):
        logger.info('QueryMiddleware:process_request()')
        if request.META['REQUEST_URI'].startswith('/archive/search/'):
            if not request.GET.get('f_list'):
                # if the query isn't already stored, get facets and store
                if request.META['QUERY_STRING'] not in request.session['queries']:
                    # call search function from here
                    base_facets = None
                    request.session['queries'][reqest.META['QUERY_STRING']] = base_facets
                    #assert False, request
        return None