import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext

from mlarchive.archive import actions
from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import EmailList, Message
from mlarchive.archive.view_funcs import get_browse_list
from mlarchive.utils.decorators import check_access, superuser_only

@superuser_only
@jsonapi
def ajax_admin_action(request):
    """Ajax function to perform action on a message"""
    if request.method == 'GET':
        #assert False, request.GET
        #return
        action = request.GET.get('action')
        id = request.GET.get('id')
        func = getattr(actions, action)
        #selected = request.POST.getlist('_selected_action')
        queryset = Message.objects.filter(pk=id)
        func(request, queryset)
        return { 'success' : True }

    if request.method == 'POST':
        assert False, request.POST
        

@check_access
def ajax_get_msg(request, msg):
    """Ajax method to retrieve message details.  One URL parameter expected, "id" which
    is the ID of the message.  Return an HTMLized message body via get_body_html().
    NOTE: the "msg" argument is Message object added by the check_access decorator
    """
    return HttpResponse(msg.get_body_html(request))


def ajax_messages(request):
    """Ajax function to retrieve more messages from queryset.  Expects one of two args:
    lastitem: return set of messages after lastitem
    firstitem: return set of messages before firstitem
    """
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    queryid = request.GET.get('queryid')
    lastitem = int(request.GET.get('lastitem',0))
    firstitem = int(request.GET.get('firstitem',0))
    query = cache.get(queryid)
    browse_list = get_browse_list(request)

    if query:
        if lastitem:
            # lastitem from request is 0 based, slice below is 1 based
            results = query[lastitem:lastitem+buffer]
        elif firstitem:
            start = firstitem - buffer if firstitem > buffer else 0
            results = query[start:firstitem]
    else:
        # TODO or fail?, signal to reload query
        return HttpResponse(status=404)     # Request Timeout (query gone from cache)

    if not results:
        return HttpResponse(status=204)     # No Content

    return render_to_response('includes/results_divs.html', {
        'results': results,
        'queryid': queryid,
        'browse_list': browse_list},
        RequestContext(request, {}),
    )

