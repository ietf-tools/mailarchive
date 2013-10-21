try:
    import json
except ImportError:
    import simplejson as json

from django.http import HttpResponse
from django.template import RequestContext
from django.template.loader import render_to_string
from django.shortcuts import render_to_response
from mlarchive.archive.models import EmailList

import mailbox
import operator

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def get_noauth(request):
    '''
    This function takes a request object and returns a list of private email list names (as string)
    the user does NOT have access to, for use in an exclude().  The list is stored in the request
    session to minimize database hits.
    '''
    noauth = request.session.get('noauth',None)
    if noauth:
        return noauth
    else:
        request.session['noauth'] = [ str(x.name) for x in EmailList.objects.filter(
            private=True).exclude(members=request.user) ]
        return request.session['noauth']

def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data),
                mimetype='application/json')
    return to_json

def render(template, data, request):
    return render_to_response(template,
                              data,
                              context_instance=RequestContext(request))

def template(template):
    def decorator(fn):
        def render(request, *args, **kwargs):
            context_data = fn(request, *args, **kwargs)
            if isinstance(context_data, HttpResponse):
                # View returned an HttpResponse like a redirect
                return context_data
            else:
                # For any other type of data try to populate a template
                return render_to_response(template,
                        context_data,
                        context_instance=RequestContext(request)
                    )
        return render
    return decorator

def sort_query(qs):
    '''Sort the given query by thread'''
    # pass one, create thread-latest_date mapping
    map = {}
    for item in qs:
        val = map.get(item.object.thread.id,None)
        if not val:
            map[item.object.thread.id] = item.date
            continue
        if val < item.date:
            map[item.object.thread.id] = item.date

    # order map by date
    map = sorted(map.iteritems(),key=operator.itemgetter(1))
    order = { x[0]:i for i,x in enumerate(map) }

    # build return set
    result = sorted(qs, key=lambda x: (order[x.object.thread.id],x.date),reverse=True)

    return result