# Copyright The IETF Trust 2007, All Rights Reserved

from django.conf import settings
from mlarchive import __date__, __rev__, __version__, __id__
from mlarchive.middleware import has_filters, get_base_query

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Context Processors
# --------------------------------------------------
def server_mode(request):
    return {'server_mode': settings.SERVER_MODE}

def revision_info(request):
    return {'revision_time': __date__[7:32], 'revision_date': __date__[7:17], 'revision_num': __rev__[6:-2], "revision_id": __id__[5:-2], "version_num": __version__ }

def facet_info(request):
    '''
    This custom context processor works in conjunction with QueryMiddleware.  If the request is
    a search query we look up the query in request.session['queries'] to retrieve the base facet
    counts.  If the query string contains a search filter parameter we need to remove before
    performing the lookup in order to retain all the filter options from the original query.
    Sessions should be set to expire after 24 hours to avoid the counts getting stale.
    TODO: alternatively this could just overwrite "facets" when a filter has been applied.
    '''
    if request.get_full_path().startswith('/archive/search/'):
        # strip any filters and lookup query
        query = get_base_query(request.GET)
        base_facets = request.session['queries'].get(query)
        logger.info('context_processer: checking for: %s' % query)
        # logger.info('context_processer: result: %s' % base_facets)
        logger.info('context_processer: contents: %s' % request.session['queries'].keys())
        return {'base_facets':base_facets}
    else:
        return {}