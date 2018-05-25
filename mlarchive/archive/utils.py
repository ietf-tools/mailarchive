
import json
from collections import OrderedDict

from django.core.cache import cache, caches
from django.http import HttpResponse


from mlarchive.archive.models import EmailList
from mlarchive.utils.test_utils import get_search_backend

THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def get_noauth(user):
    """This function takes a User object and returns a list of private email list names
    the user does NOT have access to, for use in an exclude().
    """
    # noauth_cache = caches['noauth']
    # if user.is_anonymous:
    #     user_id = 0
    # else:
    #     user_id = user.id

    # key = '{:04d}-noauth'.format(user_id)
    # noauth = noauth_cache.get(key)
    # if noauth is not None:
    #     return noauth

    if user.is_superuser:
        lists = []
    elif user.is_authenticated:
        lists = [x.name for x in EmailList.objects.filter(private=True).exclude(members=user)]
    else:
        lists = [x.name for x in EmailList.objects.filter(private=True)]
    if get_search_backend() == 'xapian':
        lists = [x.replace('-', ' ') for x in lists]
    # noauth_cache.set(key, lists, 60 * 60 * 48)
    return lists


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


def get_lists_for_user(user):
    """Returns names of EmailLists the user has access to"""
    if not user.is_authenticated:
        return get_public_lists()

    if user.is_authenticated():
        if user.is_superuser:
            lists = get_lists()
        else:
            lists = EmailList.objects.all().exclude(name__in=get_noauth(user))
            lists = OrderedDict([(k, None) for k in lists])

    return lists


def get_purge_cache_urls(message, created=True):
    """Retuns a list of absolute urls to purge from cache when message
    is created or deleted
    """
    # all messages in thread
    if created:
        urls = [m.get_absolute_url_with_host() for m in message.thread.message_set.all().exclude(pk=message.pk)]
    else:
        urls = [m.get_absolute_url_with_host() for m in message.thread.message_set.all()]
    # previous and next by date
    next_in_list = message.next_in_list()
    if next_in_list:
        urls.append(next_in_list.get_absolute_url_with_host())
    previous_in_list = message.previous_in_list()
    if previous_in_list:
        urls.append(previous_in_list.get_absolute_url_with_host())
    # index pages
    urls.extend(message.get_absolute_static_index_urls())
    # dedupe
    urls = list(set(urls))
    return urls


def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data), content_type='application/json')
    return to_json
