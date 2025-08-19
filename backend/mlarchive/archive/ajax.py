from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers, patch_cache_control

from mlarchive.archive import actions
from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import Message
from mlarchive.archive.query_utils import get_cached_query, get_order_fields, get_qdr_kwargs
from mlarchive.utils.decorators import check_access, superuser_only, check_ajax_list_access


@superuser_only
@jsonapi
def ajax_admin_action(request):
    '''Ajax function to perform action on a message'''
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
        if ids and isinstance(ids, str):
            ids = ids.split(',')
        else:
            return {'success': False}
        func = getattr(actions, action)
        queryset = Message.objects.filter(pk__in=ids)
        func(request, queryset)
        return {'success': True}


@check_access
def ajax_get_msg(request, msg):
    '''Ajax method to retrieve message details.  One URL parameter expected, "id" which
    is the ID of the message.  Return an HTMLized message body via get_body_html().
    NOTE: the "msg" argument is Message object added by the check_access decorator
    NOTE: msg_thread changes avg response time from ~100ms to ~200ms
    '''
    response = render(request, 'archive/message_ajax.html', {'msg': msg})

    if msg.email_list.private:
        add_never_cache_headers(response)
    else:
        patch_cache_control(response, max_age=86400)
    return response


@check_ajax_list_access
def ajax_messages(request):
    '''Ajax function to retrieve more messages from queryset.
    referenceitem: index of the last/first message displayed
    referenceid: message.pk of last/first message displayed
    '''
    qid = request.GET.get('qid')
    browselist = request.GET.get('browselist')
    referenceitem = int(request.GET.get('referenceitem', 0))
    referenceid = request.GET.get('referenceid')
    direction = request.GET.get('direction')
    gbt = request.GET.get('gbt')
    order_fields = get_order_fields(request.GET, use_db=True)
    qdr_kwargs = get_qdr_kwargs(request.GET)
    results = []

    if qid:
        queryid, query = get_cached_query(request)
        if not query:
            return HttpResponse(status=404)
        results = get_query_results(query, referenceitem, direction)

    elif browselist:
        # if browselist and special order fields
        if qdr_kwargs or request.GET.get('so'):
            query = Message.objects.filter(email_list__name=browselist).order_by(*order_fields)
            if qdr_kwargs:
                query = query.filter(**qdr_kwargs)
            results = get_query_results_orm(query, referenceitem, direction)
        # --------------------------------------
        else:
            try:
                reference_message = Message.objects.get(pk=referenceid, email_list__name=browselist)
            except (Message.DoesNotExist, ValueError):
                return HttpResponse(status=204)
            results = get_browse_results(reference_message, direction, gbt)

    if not results:
        return HttpResponse(status=204)     # No Content

    return render(request, 'includes/results_divs.html', {
        'results': results,
        'browse_list': browselist})


def get_query_results(query, referenceitem, direction):
    '''Returns a set of messages from query using direction: next or previous
    from the referenceitem, which is the 1 based index of the query
    '''
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    if direction == 'next':
        query = query[referenceitem:referenceitem + buffer]
        return query.execute()
    elif direction == 'previous':
        start = referenceitem - buffer if referenceitem > buffer else 0
        query = query[start:referenceitem]
        return query.execute()


def get_query_results_orm(query, referenceitem, direction):
    '''Returns a set of messages from query using direction: next or previous
    from the referenceitem, which is the 1 based index of the query
    '''
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    if direction == 'next':
        return query[referenceitem:referenceitem + buffer]
        
    elif direction == 'previous':
        start = referenceitem - buffer if referenceitem > buffer else 0
        return query[start:referenceitem]


def get_browse_results(reference_message, direction, gbt):
    '''Call appropriate low-level function based on group-by-thread (gbt)'''
    if gbt:
        return get_browse_results_gbt(reference_message, direction)
    else:
        return get_browse_results_date(reference_message, direction)


def get_browse_results_gbt(reference_message, direction):
    '''Returns a set of messages grouped by thread.  Because default ordering
    is date descending, direction "next" calls get_previous() and "previous"
    vice versa.
    '''
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
            results = list(thread.message_set.order_by('thread_order')) + results
            thread = thread.get_next()
    return results


def get_browse_results_date(reference_message, direction):
    '''Returns a set of messages ordered by date'''
    buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
    if direction == 'next':
        results = Message.objects.filter(
            email_list=reference_message.email_list,
            date__lt=reference_message.date,
        ).order_by('-date')[:buffer]
    elif direction == 'previous':
        query = Message.objects.filter(
            email_list=reference_message.email_list,
            date__gt=reference_message.date,
        ).order_by('date')[:buffer]
        results = list(query)
        results.reverse()
    return results
