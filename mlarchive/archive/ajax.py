import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.template.loader import render_to_string

from mlarchive.archive import actions
from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import EmailList, Message
from mlarchive.archive.query_utils import get_cached_query
from mlarchive.archive.view_funcs import get_browse_list
from mlarchive.utils.decorators import check_access, superuser_only

@superuser_only
@jsonapi
def ajax_admin_action(request):
    """Ajax function to perform action on a message"""
    if request.method == 'GET':
        action = request.GET.get('action')
        id = request.GET.get('id')
        func = getattr(actions, action)
        queryset = Message.objects.filter(pk=id)
        func(request, queryset)
        return { 'success' : True }

    if request.method == 'POST':
        action = request.POST.get('action')
        ids = request.POST.get('ids')
        if ids and isinstance(ids, basestring):
            ids = ids.split(',')
        else:
            return { 'success' : False }
        func = getattr(actions, action)
        queryset = Message.objects.filter(pk__in=ids)
        func(request, queryset)
        return { 'success' : True }


@check_access
def ajax_get_msg(request, msg):
    """Ajax method to retrieve message details.  One URL parameter expected, "id" which
    is the ID of the message.  Return an HTMLized message body via get_body_html().
    NOTE: the "msg" argument is Message object added by the check_access decorator
    NOTE: msg_thread changes avg response time from ~100ms to ~200ms
    """
    msg_body = msg.get_body_html(request)
    msg_thread = render_to_string('includes/message_thread.html', {
        'replies':msg.replies.all(),
        'references':msg.get_references_messages()
    })
    return HttpResponse(msg_body + msg_thread)


def ajax_messages(request):
    """Ajax function to retrieve more messages from queryset.  Expects one of two args:
    lastitem: return set of messages after lastitem
    firstitem: return set of messages before firstitem
    """
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    lastitem = int(request.GET.get('lastitem',0))
    firstitem = int(request.GET.get('firstitem',0))
    queryid, query = get_cached_query(request)
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

