from __future__ import absolute_import, division, print_function, unicode_literals

import base64
import hashlib
import json
import logging
import os
import re
import requests
import subprocess
from collections import OrderedDict

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import signals
from django.http import HttpResponse


from mlarchive.archive.models import EmailList
from mlarchive.archive.signals import _export_lists, _list_save_handler
from mlarchive.utils.test_utils import get_search_backend

logger = logging.getLogger('mlarchive.custom')
THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
LIST_LISTS_PATTERN = re.compile(r'\s*([\w\-]*) - (.*)$')

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


def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data), content_type='application/json')
    return to_json


def lookup_user(address):
    '''
    This function takes an email address and looks in Datatracker for an associated
    Datatracker account name.  Returns None if the email is not found or if there is no
    associated User account.
    '''
    apikey = settings.DATATRACKER_PERSON_ENDPOINT_API_KEY
    url = settings.DATATRACKER_PERSON_ENDPOINT
    data = {'apikey': apikey, '_expand': 'user', 'email': address}

    try:
        response = requests.post(url, data)
    except requests.exceptions.RequestException as error:
        logger.error(str(error))
        return None

    if response.status_code != 200:
        logger.error('Call to %s returned error %s' % (url, response.status_code))
        return None

    try:
        output = response.json()
        person_id = list(output['person.person'])[0]
        username = output['person.person'][person_id]['user']['username']
    except (TypeError, LookupError) as error:
        logger.error(str(error))
        return None

    return username


def process_members(email_list, emails):
    '''
    This function takes an EmailList object and a list of emails, from the mailman list_members
    command and creates the appropriate list membership relationships
    '''
    email_mapping = {}
    members = email_list.members.all()
    for email in emails:
        if email in email_mapping:
            name = email_mapping[email]
        else:
            name = lookup_user(email)
            email_mapping[email] = name

        if name:
            user, created = User.objects.get_or_create(username=name)
            if user not in members:
                email_list.members.add(user)


def get_membership(options, args):
    list_members_cmd = os.path.join(settings.MAILMAN_DIR, 'bin/list_members')
    list_lists_cmd = os.path.join(settings.MAILMAN_DIR, 'bin/list_lists')

    # disconnect the EmailList post_save signal, we don't want to call it multiple
    # times if many lists memberships have changed
    signals.post_save.disconnect(_list_save_handler, sender=EmailList)
    has_changed = False

    known_lists = []
    output = subprocess.check_output([list_lists_cmd]).splitlines()
    for line in output:
        match = LIST_LISTS_PATTERN.match(line)
        if match:
            known_lists.append(match.groups()[0].lower())

    for mlist in EmailList.objects.filter(private=True, name__in=known_lists, active=True):
        if not options.quiet:
            print("Processing: %s" % mlist.name)

        try:
            output = subprocess.check_output([list_members_cmd, mlist.name])
        except subprocess.CalledProcessError:
            continue

        sha = hashlib.sha1(output)
        digest = base64.urlsafe_b64encode(sha.digest())
        if mlist.members_digest != digest:
            has_changed = True
            process_members(mlist, output.split())
            mlist.members_digest = digest
            mlist.save()

    if has_changed:
        _export_lists()
