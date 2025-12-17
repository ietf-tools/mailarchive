import email
from email import policy
import json
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


def login_testing_unauthorized(client, url, username='staff@example.com'):
    '''Utility function to test url access'''
    response = client.get(url)
    assert response.status_code in (302, 403, 405)
    if response.status_code == 302:
        assert '/accounts/login' in response['Location']
    return client.login(username=username, password='password')


def is_email_message(byte_data):
    msg = email.message_from_bytes(byte_data, policy=policy.default)
    # Basic check: Does it have essential headers?
    important_headers = ['From', 'To', 'Subject', 'Date']
    has_headers = any(header in msg for header in important_headers)
    return has_headers


def is_json(my_str):
    try:
        json.loads(my_str)
        return True
    except (ValueError, TypeError):
        return False
