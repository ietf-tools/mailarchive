from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from mlarchive.archive import actions
from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import Message
from mlarchive.archive.query_utils import get_cached_query
from mlarchive.utils.decorators import check_access, superuser_only, check_ajax_list_access


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
        return {'success': True}

    if request.method == 'POST':
        action = request.POST.get('action')
        ids = request.POST.get('ids')
        if ids and isinstance(ids, basestring):
            ids = ids.split(',')
        else:
            return {'success': False}
        func = getattr(actions, action)
        queryset = Message.objects.filter(pk__in=ids)
        func(request, queryset)
        return {'success': True}


@check_access
def ajax_get_msg(request, msg):
    """Ajax method to retrieve message details.  One URL parameter expected, "id" which
    is the ID of the message.  Return an HTMLized message body via get_body_html().
    NOTE: the "msg" argument is Message object added by the check_access decorator
    NOTE: msg_thread changes avg response time from ~100ms to ~200ms
    """
    msg_body = msg.get_body_html(request)
    msg_thread = render_to_string('includes/message_thread.html', {'msg': msg})
    return HttpResponse(msg_body + msg_thread)


@check_ajax_list_access
def ajax_messages(request):
    """Ajax function to retrieve more messages from queryset.  Expects one of two args:
    lastitem: return set of messages after lastitem
    firstitem: return set of messages before firstitem
    """
    queryid, query = get_cached_query(request)
    browselist = request.GET.get('browselist')
    referenceitem = int(request.GET.get('referenceitem', 0))
    referenceid = request.GET.get('referenceid')
    direction = request.GET.get('direction')
    gbt = request.GET.get('gbt')
    results = []

    if query:
        results = get_query_results(query, referenceitem, direction)
    elif browselist:
        results = get_browse_results(referenceid, direction, gbt)
    else:
        # TODO or fail?, signal to reload query
        return HttpResponse(status=404)     # Request Timeout (query gone from cache)

    if not results:
        return HttpResponse(status=204)     # No Content

    return render(request, 'includes/results_divs.html', {'results': results, 'browse_list': browselist})


def get_query_results(query, referenceitem, direction):
    '''Returns a set of messages from query using direction: next or previous
    from the referenceitem, which is the 1 based index of the query'''
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    if direction == 'next':
        return query[referenceitem:referenceitem + buffer]
    elif direction == 'previous':
        start = referenceitem - buffer if referenceitem > buffer else 0
        return query[start:referenceitem]


def get_browse_results(referenceid, direction, gbt):
    '''Call appropriate low-level function based on group-by-thread (gbt)'''
    reference_message = Message.objects.get(pk=referenceid)
    if gbt:
        return get_browse_results_gbt(reference_message, direction)
    else:
        return get_browse_results_date(reference_message, direction)


def get_browse_results_gbt(reference_message, direction):
    '''Returns a set of messages grouped by thread.  Because default ordering is date descending,
    direction "next" calls get_previous() and "previous" vice versa.'''
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    results = []
    if direction == 'next':
        thread = reference_message.thread.get_previous()
        while len(results) < buffer and thread:
            results.extend(thread.message_set.order_by('thread_order'))
            thread = thread.get_previous()
    elif direction == 'previous':
        thread = reference_message.thread.get_next()
        while len(results) < buffer and thread:
            # prepend to results
            results = thread.message_set.order_by('thread_order') + results
            thread = thread.get_next()
    return results


def get_browse_results_date(reference_message, direction):
    '''Returns a set of messages ordered by date'''
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    if direction == 'next':
        results = Message.objects.filter(email_list=reference_message.email_list, date__lt=reference_message.date).order_by('-date')[:buffer]
    elif direction == 'previous':
        results = Message.objects.filter(email_list=reference_message.email_list, date__gt=reference_message.date).order_by('date')[:buffer]
        results.reverse()
    return results
