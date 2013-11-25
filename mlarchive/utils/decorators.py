from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render_to_response, get_object_or_404
from functools import wraps
from mlarchive.archive.models import Message

import datetime

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')


def check_access(func):
    """
    This decorator checks that the user making the request has access to the
    Message being requested.  Expects "id" as an argument, in the case of a regular
    view URL, or "id" as a URL parameter, in the case of an AJAX request.  It also
    adds the message object to the function arguments so we don't have to repeat the
    lookup.
    """
    def wrapper(request, *args, **kwargs):
        # if passed as a URL parameter id is a record id (more common)
        if request.GET.has_key('id'):
            msg = get_object_or_404(Message,id=request.GET['id'])
        # if passed as a function argument id is a hashcode (less common)
        elif 'id' in kwargs:
            msg = get_object_or_404(Message,hashcode=kwargs['id'])
        else:
            raise Http404

        if msg.email_list.private and not request.user.is_superuser:
            if not request.user.is_authenticated() or not msg.email_list.members.filter(id=request.user.id):
                raise PermissionDenied
        else:
            # add the message object to returning arguments
            kwargs['msg'] = msg
            return func(request, *args, **kwargs)

    return wraps(func)(wrapper)

def check_datetime(func):
    '''
    This decorator checks the datetime return value of func for dates incorrectly derived
    from two digit years and fixes them.
    '''
    def wrapper(*args, **kwargs):
        dt = func(*args, **kwargs)
        if isinstance(dt,datetime.datetime):
            if 69 <= dt.year < 100:
                dt = datetime.datetime(dt.year + 1900,dt.month,dt.day,dt.hour,dt.minute)
            elif 0 <= dt.year < 69:
                dt = datetime.datetime(dt.year + 2000,dt.month,dt.day,dt.hour,dt.minute)
        return dt
    return wraps(func)(wrapper)

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

def superuser_only(function):
    '''
    Limit view to superusers only.
    '''
    def _inner(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return function(request, *args, **kwargs)
    return _inner