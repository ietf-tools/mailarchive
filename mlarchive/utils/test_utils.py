from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage

def get_request(url='/',user=None):
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
