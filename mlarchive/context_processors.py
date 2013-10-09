from django.conf import settings
from mlarchive import __date__, __rev__, __version__, __id__
from mlarchive.middleware import get_base_query

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Context Processors
# --------------------------------------------------
def server_mode(request):
    'A context procesor that provides server_mode'
    return {'server_mode': settings.SERVER_MODE}

def revision_info(request):
    'A context processor that provides version and svn revision info'
    return {'revision_time': __date__[7:32],
            'revision_date': __date__[7:17],
            'revision_num': __rev__[6:-2],
            'revision_id': __id__[5:-2], 
            'version_num': __version__ }

def facet_info(request):
    '''
    A context processor that works in conjunction with QueryMiddleware.  If the request is
    a search query we look up the query in request.session['queries'] to retrieve the base facet
    counts.  We need use the base query, for lookup, which is the query stripped of any filter,
    sorting, or paging parameters.
    Sessions should be set to expire after 2 hours to avoid the counts getting stale.
    TODO: alternatively this could just overwrite "facets" when a filter has been applied.
    '''
    if request.get_full_path().startswith('/archive/search/'):
        query = get_base_query(request.GET)
        base_facets = request.session['queries'].get(query)
        logger.info('context_processer: checking for: %s' % query)
        # logger.info('context_processer: result: %s' % base_facets)
        logger.info('context_processer: contents: %s' % request.session['queries'].keys())
        return {'base_facets':base_facets}
    else:
        return {}