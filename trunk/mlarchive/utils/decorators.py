from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render_to_response, get_object_or_404
from functools import wraps
from mlarchive.archive.models import Message

def superuser_only(function):
    '''
    Limit view to superusers only.
    '''
    def _inner(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied           
        return function(request, *args, **kwargs)
    return _inner

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


