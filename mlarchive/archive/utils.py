import json
from collections import OrderedDict

from django.core.cache import cache
from django.http import HttpResponse

from mlarchive.archive.models import EmailList
from mlarchive.utils.test_utils import get_search_backend

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def get_noauth(request):
    """This function takes a request object and returns a list of private email list names
    the user does NOT have access to, for use in an exclude().  The list is
    stored in the request session to minimize database hits.
    """
    noauth = request.session.get('noauth', None)
    if noauth:
        return noauth

    if request.user.is_superuser:
        lists = []
    elif request.user.is_authenticated:
        lists = [x.name for x in EmailList.objects.filter(private=True).exclude(members=request.user)]
    else:
        lists = [x.name for x in EmailList.objects.filter(private=True)]
    if get_search_backend() == 'xapian':
        lists = [x.replace('-', ' ') for x in lists]
    request.session['noauth'] = lists
    return request.session['noauth']


def get_lists():
    """Returns OrderedDict of all EmailLists"""
    lists = cache.get('lists')
    if lists:
        return lists
    else:
        lists = EmailList.objects.all().order_by('name').values_list('name', flat=True)
        lists = OrderedDict([(k, None) for k in lists])
        cache.set('lists', lists)
        return lists


def get_public_lists():
    lists = cache.get('lists_public')
    if lists:
        return lists
    else:
        public = EmailList.objects.filter(private=False).order_by('name').values_list('name', flat=True)
        lists = OrderedDict([(k, None) for k in public])
        cache.set('lists_public', lists)
        return lists


def get_lists_for_user(request):
    """Returns names of EmailLists the user has access to"""
    if not request.user.is_authenticated:
        return get_public_lists()

    if request.user.is_authenticated():
        if request.user.is_superuser:
            lists = get_lists()
        else:
            lists = EmailList.objects.all().exclude(name__in=get_noauth(request))
            lists = OrderedDict([(k, None) for k in lists])

    return lists


def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data), content_type='application/json')
    return to_json
