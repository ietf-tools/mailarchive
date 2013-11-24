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

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

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
        request.session['noauth'] = [ str(x.id) for x in EmailList.objects.filter(
            private=True).exclude(members=request.user) ]
        return request.session['noauth']

def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data),
                mimetype='application/json')
    return to_json

def log_timing(func):
    '''
    This is a decorator that logs the time it took to complete the decorated function.
    Handy for performance testing
    '''
    def wrapper(*arg):
        t1 = time.time()
        res = func(*arg)
        t2 = time.time()
        logger.info('%s took %0.3f ms' % (func.func_name, (t2-t1)*1000.0))
        return res
    return wrapper

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
