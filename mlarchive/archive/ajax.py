import json

from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.utils import simplejson

from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import EmailList, Message
from mlarchive.utils.decorators import check_access

@jsonapi
def ajax_get_list(request):
    """Ajax function for use with jQuery UI Autocomplete.  Returns list of EmailList
    objects that start with value of "term" GET parameter.
    """
    if request.method != 'GET' or not request.GET.has_key('term'):
        return { 'success' : False, 'error' : 'No term submitted or not GET' }
    term = request.GET.get('term')
    user = request.user

    results = EmailList.objects.filter(name__startswith=term)
    if not user.is_authenticated():
        results = results.exclude(private=True)
    else:
        results = results.filter(Q(private=False)|Q(private=True,members=user))

    if results.count() > 20:
        results = results[:20]
    elif results.count() == 0:
        return { 'success' : False, 'error' : "No results" }

    response = [dict(id=r.id, label = r.name) for r in results]
    return response

@check_access
def ajax_get_msg(request, msg):
    """Ajax method to retrieve message details.  One URL parameter expected, "id" which
    is the ID of the message.  Return an HTMLized message body via get_body_html().
    NOTE: the "msg" argument is Message object added by the check_access decorator
    """
    return HttpResponse(msg.get_body_html(request))

def ajax_messages(request):
    """Ajax function to retrieve next 25 messages from the cached queryset
    """
    queryid = request.GET.get('queryid')
    lastitem = int(request.GET.get('lastitem'))
    query = cache.get(queryid)

    if query:
        # lastitem from request is 0 based, slice below is 1 based
        results = query[lastitem:lastitem+25]
    else:
        # TODO or fail?, signal to reload query
        return HttpResponse(status=404)     # Request Timeout (query gone from cache)

    if not results:
        return HttpResponse(status=204)     # No Content

    return render_to_response('includes/results_rows.html', {
        'results': results},
        RequestContext(request, {}),
    )

