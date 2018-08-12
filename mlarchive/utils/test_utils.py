import email
import os


from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from haystack.query import SearchQuerySet
from django.test import RequestFactory


def get_request(url='/', user=None):
    """Returns an HTTPRequest object suitable for testing a view.  Includes all
    attributes to support Middelware"""
    rf = RequestFactory()
    request = rf.get(url)
    setattr(request, 'session', {})
    if user:
        setattr(request, 'user', user)
    else:
        setattr(request, 'user', AnonymousUser)
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)
    return request


def get_search_backend():
    backend = type(SearchQuerySet().query.backend).__name__.lower()
    if 'xapian' in backend:
        return 'xapian'
    elif 'elasticsearch' in backend:
        return 'elasticsearch'


def message_from_file(filename):
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path) as f:
        msg = email.message_from_file(f)
    return msg
