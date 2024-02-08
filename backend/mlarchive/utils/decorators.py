import datetime
import os
import time

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from functools import wraps
from mlarchive.archive.models import Message, EmailList, Redirect

import logging
logger = logging.getLogger(__name__)


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
        if request.GET.get('id', '').isdigit():
            msg = get_object_or_404(Message.objects.select_related(), id=request.GET['id'])
        # if passed as a function argument id is a hashcode (less common)
        elif 'id' in kwargs:
            try:
                msg = Message.objects.get(hashcode=kwargs['id'], email_list__name=kwargs['list_name'])
            except Message.DoesNotExist: 
                # look in redirect table
                try:
                    redir = Redirect.objects.get(old=request.get_full_path())
                    return redirect(redir.new, permanent=True)
                except Redirect.DoesNotExist:
                    pass
                # look in _removed
                try:
                    email_list = EmailList.objects.get(name=kwargs['list_name'])
                except EmailList.DoesNotExist:
                    raise Http404
                hashcode = kwargs['id']
                if not hashcode.endswith('='):
                    hashcode = hashcode + '='
                path = os.path.join(email_list.removed_dir, hashcode)
                if os.path.exists(path):
                    return render(request, 'archive/removed.html', {}, status=410)
                raise Http404
        else:
            raise Http404

        if msg.email_list.private and not request.user.is_superuser:
            if not request.user.is_authenticated or not msg.email_list.members.filter(id=request.user.id):
                raise PermissionDenied

        kwargs['msg'] = msg
        return func(request, *args, **kwargs)

    return wraps(func)(wrapper)


def check_list_access(func):
    """
    This decorator checks that the user making the request has access to the
    list being requested.  Expects list_name as an argument.
    """
    def wrapper(request, *args, **kwargs):
        try:
            email_list = EmailList.objects.get(name=kwargs['list_name'])
        except EmailList.DoesNotExist:
            raise Http404

        if email_list.private and not request.user.is_superuser:
            if not request.user.is_authenticated or not email_list.members.filter(id=request.user.id):
                raise PermissionDenied

        kwargs['email_list'] = email_list
        return func(request, *args, **kwargs)

    return wraps(func)(wrapper)


def check_ajax_list_access(func):
    """
    This decorator checks that the user making the request has access to the
    list being requested.
    """
    def wrapper(request, *args, **kwargs):
        listname = request.GET.get('browselist')
        if not listname:
            return func(request, *args, **kwargs)
        try:
            email_list = EmailList.objects.get(name=listname)
        except EmailList.DoesNotExist:
            raise Http404

        if email_list.private and not request.user.is_superuser:
            if not request.user.is_authenticated or not email_list.members.filter(id=request.user.id):
                raise PermissionDenied

        return func(request, *args, **kwargs)

    return wraps(func)(wrapper)


def check_datetime(func):
    '''
    This decorator checks the datetime return value of func for dates incorrectly derived
    from two digit years and fixes them.
    '''
    def wrapper(*args, **kwargs):
        dt = func(*args, **kwargs)
        if isinstance(dt, datetime.datetime):
            if 69 <= dt.year < 100:
                dt = datetime.datetime(dt.year + 1900, dt.month, dt.day, dt.hour, dt.minute)
            elif 0 <= dt.year < 69:
                dt = datetime.datetime(dt.year + 2000, dt.month, dt.day, dt.hour, dt.minute)
        return dt
    return wraps(func)(wrapper)


def pad_id(func):
    '''
    This decorator checks to see if we've received an unpadded message id and pads it.
    '''
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'id' in kwargs and not kwargs['id'].endswith("="):
            kwargs['id'] = kwargs['id'] + "="
        return func(*args, **kwargs)
    return wrapper


def log_timing(func):
    '''
    This is a decorator that logs the time it took to complete the decorated function.
    Handy for performance testing
    '''
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.info('Function Time: %s took %0.3f ms' % (__name__, (end - start) * 1000.0))
        return result
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


def staff_only(function):
    '''
    Limit view to staff only.
    '''
    def _inner(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return function(request, *args, **kwargs)
    return _inner


def require_api_key(f):
    @wraps(f)
    def _wrapper(request, *args, **kwargs):
        def err(code, text):
            return JsonResponse({'error': text}, status=code)
        apikey = None
        # Check method and get hash
        if request.method == 'POST':
            if 'apikey' in request.POST:
                apikey = request.POST.get('apikey')
            elif 'X-API-Key' in request.headers:
                apikey = request.headers.get('X-API-Key')
        elif request.method == 'GET':
            apikey = request.GET.get('apikey')
        else:
            return err(405, "Method not allowed")
        if not apikey:
            return err(400, "Missing apikey")

        # Check apikey
        if apikey not in settings.API_KEYS:
            return err(403, "Invalid apikey")

        # Check endpoint
        urlpath = request.META.get('PATH_INFO')
        if not (urlpath.startswith(settings.API_KEYS[apikey])):
            return err(400, "Apikey endpoint mismatch")

        # Execute decorated function
        try:
            ret = f(request, *args, **kwargs)
        except AttributeError as e:
            logger.error("Bad API call: args: %s, kwargs: %s, exception: %s" % (args, kwargs, e))
            return err(400, "Bad or missing parameters")
        return ret
    return _wrapper
