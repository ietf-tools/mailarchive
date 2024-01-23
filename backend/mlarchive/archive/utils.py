from builtins import input

import base64
import datetime
import email
import hashlib
import json
import logging
import mailbox
import os
import re
import requests
import subprocess


from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.encoding import smart_bytes
from mlarchive.archive.models import EmailList, Subscriber
# from mlarchive.archive.signals import _export_lists, _list_save_handler


logger = logging.getLogger(__name__)
THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
LIST_LISTS_PATTERN = re.compile(r'\s*([\w\-]*) - (.*)$')


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def _export_lists():
    """Write XML dump of list / memberships and call external program"""

    # Dump XML
    data = _get_lists_as_xml()
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    try:
        if not os.path.exists(settings.EXPORT_DIR):
            os.mkdir(settings.EXPORT_DIR)
        with open(path, 'w') as file:
            file.write(data)
            os.chmod(path, 0o666)
    except Exception as error:
        logger.error('Error creating export file: {}'.format(error))
        return

    # Call external script
    if hasattr(settings, 'NOTIFY_LIST_CHANGE_COMMAND'):
        command = settings.NOTIFY_LIST_CHANGE_COMMAND
        try:
            subprocess.check_call([command, path])
        except (OSError, subprocess.CalledProcessError) as error:
            logger.error('Error calling external command: {} ({})'.format(command, error))


def _get_lists_as_xml():
    """Returns string: XML of lists / membership for IMAP"""
    lines = []
    lines.append("<ms_config>")

    for elist in EmailList.objects.all().order_by('name'):
        lines.append("  <shared_root name='{name}' path='/var/isode/ms/shared/{name}'>".format(name=elist.name))
        if elist.private:
            lines.append("    <user name='anonymous' access='none'/>")
            for member in elist.members.all():
                lines.append("    <user name='{name}' access='read,write'/>".format(name=member.username))
        else:
            lines.append("    <user name='anonymous' access='read'/>")
            lines.append("    <group name='anyone' access='read,write'/>")
        lines.append("  </shared_root>")
    lines.append("</ms_config>")
    return "\n".join(lines)


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
    # noauth_cache.set(key, lists, 60 * 60 * 48)
    return lists


def get_lists():
    """Returns list of all EmailList names"""
    lists = cache.get('lists')
    if lists:
        return lists
    else:
        lists = EmailList.objects.all().order_by('name').values_list('name', flat=True)
        cache.set('lists', lists)
        return lists


def get_public_lists():
    lists = cache.get('lists_public')
    if lists:
        return lists
    else:
        lists = EmailList.objects.filter(private=False).order_by('name').values_list('name', flat=True)
        cache.set('lists_public', lists)
        return lists


def get_lists_for_user(user):
    """Returns names of EmailLists the user has access to"""
    if not user.is_authenticated:
        return get_public_lists()

    if user.is_authenticated:
        if user.is_superuser:
            return get_lists()

    return EmailList.objects.all().exclude(name__in=get_noauth(user)).order_by('name').values_list('name', flat=True)


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
        response = requests.post(url, data, timeout=settings.DEFAULT_REQUESTS_TIMEOUT)
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
    for address in emails:
        if address in email_mapping:
            name = email_mapping[address]
        else:
            name = lookup_user(address)
            email_mapping[address] = name

        if name:
            try:
                user = User.objects.get(username__iexact=name)
            except User.DoesNotExist:
                user = User.objects.create(username=name)
            if user not in members:
                email_list.members.add(user)


def get_known_mailman_lists(private=None):
    '''Returns EmailLists that are managed by mailman'''
    list_lists_cmd = os.path.join(settings.MAILMAN_DIR, 'bin/list_lists')
    known_lists = []
    data = subprocess.check_output([list_lists_cmd])
    output = data.decode('ascii').splitlines()
    for line in output:
        match = LIST_LISTS_PATTERN.match(line)
        if match:
            known_lists.append(match.groups()[0].lower())
    
    mlists = EmailList.objects.filter(name__in=known_lists)
    if isinstance(private, bool):
        mlists = mlists.filter(private=private)
    return mlists


def get_mailman_lists(private=None):
    '''Returns EmailLists that are managed by mailman 3.
    Specify list.private value or leave out to retrieve all lists.
    Raises requests.RequestException if request fails.
    '''
    response = requests.get(
        settings.MAILMAN_API_LISTS,
        auth=(settings.MAILMAN_API_USER, settings.MAILMAN_API_PASSWORD),
        timeout=settings.DEFAULT_REQUESTS_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    mailman_lists = [e['list_name'] for e in data['entries']]
    mlists = EmailList.objects.filter(name__in=mailman_lists)
    if isinstance(private, bool):
        mlists = mlists.filter(private=private)
    return mlists


def get_subscribers(listname):
    '''Gets list of subscribers for listname from mailman'''
    list_members_cmd = os.path.join(settings.MAILMAN_DIR, 'bin/list_members')
    try:
        output = subprocess.check_output([list_members_cmd, listname]).decode('latin1')
    except subprocess.CalledProcessError:
        return []
    return output.split()


def get_subscribers_3(listname):
    '''Gets list of subscribers for listname from mailman 3 API'''
    response = requests.get(
        settings.MAILMAN_API_MEMBER.format(listname=listname),
        auth=(settings.MAILMAN_API_USER, settings.MAILMAN_API_PASSWORD),
        timeout=settings.DEFAULT_REQUESTS_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return [e['email'] for e in data['entries']]


def get_subscriber_count():
    '''Populates Subscriber table with subscriber counts from mailman'''
    for mlist in get_known_mailman_lists():
        Subscriber.objects.create(email_list=mlist, count=len(get_subscribers(mlist.name)))


def get_membership(options, args):
    # disconnect the EmailList post_save signal, we don't want to call it multiple
    # times if many lists memberships have changed
    # signals.post_save.disconnect(_list_save_handler, sender=EmailList)
    has_changed = False

    for mlist in get_known_mailman_lists(private=True):
        if not options.quiet:
            print("Processing: %s" % mlist.name)

        subscribers = get_subscribers(mlist.name)
        sha = hashlib.sha1(smart_bytes(subscribers))
        digest = base64.urlsafe_b64encode(sha.digest())
        if mlist.members_digest != digest:
            has_changed = True
            process_members(mlist, subscribers)
            mlist.members_digest = digest
            mlist.save()

    if has_changed:
        _export_lists()


def get_membership_3(quiet=False):
    '''For all private lists, get membership from mailman 3 API and update
    list membership as needed'''
    for mlist in get_mailman_lists(private=True):
        if not quiet:
            print("Processing: %s" % mlist.name)

        # handle these exceptions locally because calls for
        # other lists may succeed
        try:
            subscribers = get_subscribers_3(mlist.name)
        except requests.RequestException as e:
            logger.error(f'get_subscribers failed. listname={mlist.name}. {e}')
            continue
        sha = hashlib.sha1(smart_bytes(subscribers))
        digest = base64.urlsafe_b64encode(sha.digest())
        if mlist.members_digest != digest:
            process_members(mlist, subscribers)
            mlist.members_digest = digest
            mlist.save()


def check_inactive(prompt=True):
    '''Check for inactive lists and mark them as inactive'''
    active = []
    to_inactive = []

    # get active mailman lists
    output = subprocess.check_output(['/usr/lib/mailman/bin/list_lists'])
    for line in output.splitlines():
        name = line.split(' - ')[0].strip().lower()
        active.append(name)

    # get externally hosted lists
    try:
        output = subprocess.check_output(['grep', 'call-archives.py', '/a/postfix/aliases'])
    except subprocess.CalledProcessError as e:
        if e.returncode not in (0, 1):      # 1 means grep found nothing
            raise

    for line in output.splitlines():
        name = line.split()[-1].strip('"').strip().lower()
        active.append(name)

    for elist in EmailList.objects.filter(active=True).order_by('name'):
        if elist.name not in active:
            messages = elist.message_set.all().order_by('-date')
            if messages.first() and messages.first().date > datetime.datetime.today() - datetime.timedelta(days=90):
                print("{}  => inactive.  SKIPPING last message date = {}".format(elist.name, messages.first().date))
                continue
            print("{}  => inactive".format(elist.name))
            to_inactive.append(elist.name)

    if prompt:
        answer = input('Update lists y/n?')
        if answer.lower() == 'y':
            print('OK')
        else:
            return

    EmailList.objects.filter(name__in=to_inactive).update(active=False)


def create_mbox_file(month, year, elist):
    filename = '{:04d}-{:02d}.mail'.format(year, month)
    path = os.path.join(settings.ARCHIVE_MBOX_DIR, 'public', elist.name, filename)
    messages = elist.message_set.filter(date__month=month, date__year=year)
    if os.path.exists(path):
        os.remove(path)
    if messages.count() == 0:
        return
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    mbox = mailbox.mbox(path)
    for message in messages:
        with open(message.get_file_path(), 'rb') as f:
            msg = email.message_from_binary_file(f)
        mbox.add(msg)
    mbox.close()
