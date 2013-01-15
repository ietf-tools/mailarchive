from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from functools import wraps

from mlarchive.archive.models import Message
from mlarchive.http import Http403

from itertools import chain

def check_access(func):
    """
    This decorator checks that the user making the request has access to the
    Message being requested.  Expects "id" as an argument, in the case of a regular
    view URL, or "id" as a URL parameter, in the case of an AJAX request.  It also 
    adds the message object to the function arguments so we don't have to repeat the
    lookup.
    """
    def wrapper(request, *args, **kwargs):
        # if passed as a function argument id is a hashcode
        if 'id' in kwargs:
            id = kwargs['id']
            msg = get_object_or_404(Message,hashcode=id)
        # if passed as a URL parameter id is a record id
        elif request.GET.has_key('id'):
            id = request.GET['id']
            msg = get_object_or_404(Message,id=id)
        
        # add the message object to returning arguments
        kwargs['msg'] = msg
        
        # short circuit. superuser has full access
        if request.user.is_superuser:
            return func(request, *args, **kwargs)
        
        if msg.email_list.private:
            if not request.user.is_authenticated() or not msg.email_list.members.filter(id=request.user.id):
                raise Http403
        else:
            return func(request, *args, **kwargs)

    return wraps(func)(wrapper)

def admin_only(func):
    """
    This decorator checks that the user making the request is an admin user.
    """
    def wrapper(request, *args, **kwargs):
        # TODO implement for admin user
        if request.user_is_secretariat:
            return func(request, *args, **kwargs)
        
        return render_to_response('unauthorized.html',{
            'user_name':request.user.get_profile()}
        )

    return wraps(func)(wrapper)
