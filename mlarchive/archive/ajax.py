from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.utils import simplejson
from haystack.query import SearchQuerySet
from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import EmailList, Message
from mlarchive.utils.decorators import check_access

import json

@jsonapi
def ajax_get_list(request):
    '''
    Ajax function for use with jQuery UI Autocomplete.  Returns list of EmailList objects
    that start with value of "term" GET parameter.
    '''
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
    '''
    Ajax method to retrieve message details.  One URL parameter expected, "id" which
    is the ID of the message.  Return an HTMLized message body via get_body_html().
    NOTE: the "msg" argument is Message object added by the check_access decorator
    '''
    return HttpResponse(msg.get_body_html(request))

@jsonapi
def ajax_messages(request):
    '''
    Ajax function for use with ExtJS.  Supports pagination.
    '''
    kwargs = {}
    page = request.GET.get('page')
    sort = request.GET.get('sort',None)
    email_list = request.GET.get('email_list',None)

    if email_list:
        # convert comma separated names into list of IDs
        ids = []
        for name in email_list.split(','):
            try:
                ids.append(EmailList.objects.get(name=name).id)
            except EmailList.DoesNotExist:
                pass
        kwargs['email_list__in'] = ids

    # do the query
    message_list = SearchQuerySet().filter(**kwargs)

    # handle sort
    if sort:
        obj = json.loads(sort)
        by = obj[0]['property']
        if by == 'email_list':
            by = by + '.name'
        if obj[0]['direction'] == 'DESC':
            by = '-' + by
        message_list = message_list.order_by(by)

    paginator = Paginator(message_list, 200) # Show 200 messages per page

    try:
        messages = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        messages = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        messages = paginator.page(paginator.num_pages)

    results = messages.object_list
    messages = [dict(date=r.object.date.strftime('%m-%d-%Y'),
                     subject=r.object.subject,
                     frm=r.object.frm_email,
                     email_list=r.object.email_list.name) for r in results]
    response = {'success':True,
                'total':message_list.count(),
                'messages':messages}
    return response
