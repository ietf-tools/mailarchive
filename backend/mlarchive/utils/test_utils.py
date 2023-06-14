import os


from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from mlarchive.archive.mail import archive_message

# for Python 2/3 compatability
try:
    from email import message_from_binary_file
except ImportError:
    from email import message_from_file as message_from_binary_file


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


def message_from_file(filename):
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path, 'rb') as f:
        msg = message_from_binary_file(f)
    return msg


def load_message(filename, listname='public'):
    """Loads a message given path"""
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path, 'rb') as f:
        data = f.read()
    archive_message(data, listname)