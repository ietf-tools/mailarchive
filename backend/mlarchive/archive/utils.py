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
import shutil
import subprocess
from collections import defaultdict

import mailmanclient
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.encoding import smart_bytes

from mlarchive.archive.models import EmailList, Subscriber, Redirect
from mlarchive.archive.mail import MessageWrapper
# from mlarchive.archive.signals import _export_lists, _list_save_handler


logger = logging.getLogger(__name__)
THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
LIST_LISTS_PATTERN = re.compile(r'\s*([\w\-]*) - (.*)$')
MAILMAN_LISTID_PATTERN = re.compile(r'(.*)\.(ietf|irtf|iab|iesg|rfc-editor)\.org')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def _export_lists():
    """Write XML dump of list membership for IMAP"""

    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    date_string = today_utc.strftime('%Y%m%d')
    data = _get_lists_as_xml()
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.{}.xml'.format(date_string))
    tmp_path = path + '.tmp'
    try:
        if not os.path.exists(settings.EXPORT_DIR):
            os.mkdir(settings.EXPORT_DIR)
        with open(tmp_path, 'w') as file:
            file.write(data)
        os.chmod(tmp_path, 0o666)
        if os.path.exists(path):
            os.remove(path)
        os.rename(tmp_path, path)
    except Exception as error:
        logger.error('Error creating export file: {}'.format(error))
        return


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
    # check cache
    username_map = cache.get('username_map')
    if username_map and address in username_map:
        return username_map[address]

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
        person_ids = list(output['person.person'])
        if not person_ids:
            logger.warning(f'lookup_user failed for {address}')
            return None
        username = output['person.person'][person_ids[0]]['user']['username']
    except (TypeError, LookupError) as error:
        logger.error(str(error))
        return None

    if username_map is None:
        username_map = {}

    username_map[address] = username
    cache.set('username_map', username_map, timeout=None)

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
                user = User.objects.create(username=name, email=name)
            if user not in members:
                email_list.members.add(user)


def add_cloudflare_credentials(params):
    params['headers']['CF-Access-Client-Id'] = settings.MAILMAN_CF_ACCESS_CLIENT_ID
    params['headers']['CF-Access-Client-Secret'] = settings.MAILMAN_CF_ACCESS_CLIENT_SECRET
    return params


def get_mailman_lists(private=None):
    '''Returns EmailLists that are managed by mailman 3.
    Specify list.private value or leave out to retrieve all lists.
    Raises requests.RequestException if request fails.
    '''
    client = mailmanclient.Client(
        settings.MAILMAN_API_URL,
        settings.MAILMAN_API_USER,
        settings.MAILMAN_API_PASSWORD,
        request_hooks=[add_cloudflare_credentials])
    mailman_lists = [x.list_name for x in client.lists]
    email_lists = EmailList.objects.filter(name__in=mailman_lists)
    if isinstance(private, bool):
        email_lists = email_lists.filter(private=private)
    return email_lists


def fqdn_default():
    return 'ietf.org'


def get_fqdn_map():
    fqdn_map = cache.get('fqdn_map')
    if fqdn_map is None:
        fqdn_map = defaultdict(fqdn_default)
        client = mailmanclient.Client(
            settings.MAILMAN_API_URL,
            settings.MAILMAN_API_USER,
            settings.MAILMAN_API_PASSWORD,
            request_hooks=[add_cloudflare_credentials])
        for mailman_list in client.lists:
            fqdn_map[mailman_list.list_name] = mailman_list.mail_host
        cache.set('fqdn_map', fqdn_map, timeout=86400)
    return fqdn_map


def get_fqdn(listname):
    '''Returns fully qualified domain name by querying mailman'''
    fqdn_map = get_fqdn_map()
    return listname + '@' + fqdn_map[listname]


def get_subscribers(listname):
    '''Gets list of subscribers for listname from mailman'''
    client = mailmanclient.Client(
        settings.MAILMAN_API_URL,
        settings.MAILMAN_API_USER,
        settings.MAILMAN_API_PASSWORD,
        request_hooks=[add_cloudflare_credentials])
    fqdn = get_fqdn(listname)
    mailman_list = client.get_list(fqdn)
    members = mailman_list.members
    return [m.email for m in members]


def get_subscriber_counts():
    '''Populates Subscriber table with subscriber counts from mailman 3 API'''
    client = mailmanclient.Client(
        settings.MAILMAN_API_URL,
        settings.MAILMAN_API_USER,
        settings.MAILMAN_API_PASSWORD,
        request_hooks=[add_cloudflare_credentials])
    counts = {x.list_name: x.member_count for x in client.lists}
    subscribers = []
    for elist in EmailList.objects.all():
        if elist.name in counts:
            subscribers.append(Subscriber(email_list=elist, count=counts[elist.name]))
    Subscriber.objects.bulk_create(subscribers)


def get_membership_3(quiet=False):
    '''For all private lists, get membership from mailman 3 API and update
    list membership as needed.

    Initial plan was to use client.members to get all list memberships rather
    than hitting the API for every private list, but this request fails
    trying to retrieve millions of records.
    '''
    has_changed = False

    client = mailmanclient.Client(
        settings.MAILMAN_API_URL,
        settings.MAILMAN_API_USER,
        settings.MAILMAN_API_PASSWORD,
        request_hooks=[add_cloudflare_credentials])

    private_lists = get_mailman_lists(private=True)
    fqdn_map = get_fqdn_map()
    for plist in private_lists:
        if not quiet:
            print("Processing: %s" % plist)
        if plist.name not in fqdn_map:
            logger.warning("Can't find fqdn for list: {}".format(plist.name))
            continue
        fqdn = plist.name + '@' + fqdn_map[plist.name]
        mailman_list = client.get_list(fqdn)
        mailman_members = mailman_list.members
        members = [m.email for m in mailman_members]
        sha = hashlib.sha1(smart_bytes(members))
        digest = base64.urlsafe_b64encode(sha.digest())
        digest = digest.decode()
        if plist.members_digest != digest:
            has_changed = True
            process_members(plist, members)
            plist.members_digest = digest
            plist.save()

    if has_changed:
        _export_lists()


def check_inactive(prompt=True):
    '''Check for inactive lists and mark them as inactive'''
    # this won't work for mailman 3 or when postfix is moved
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


def update_mbox_files():
    '''Update archive mbox files'''
    yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    month = yesterday.month
    year = yesterday.year
    for elist in EmailList.objects.filter(active=True, private=False):
        if elist.message_set.filter(date__month=month, date__year=year).count() > 0:
            create_mbox_file(month=month, year=year, elist=elist)


def purge_incoming():
    '''Purge messages older than 90 days from incoming directory'''
    path = settings.INCOMING_DIR
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=90)
    for file in os.listdir(path):
        file_path = os.path.join(path, file)
        file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
        if file_mtime < cutoff_date:
            os.remove(file_path)


def move_list(source, target):
    '''Move messages from source list to target list. Includes:
    - create the new list if it doesn't exist
    - moving files on disk
    - updating database and search index
    - creating entries in the Redirect table to map original urls
    to new urls
    '''
    try:
        source_list = EmailList.objects.get(name=source)
    except EmailList.DoesNotExist:
        raise Exception(f'Email list does not exist: {source}')
    target_list, created = EmailList.objects.get_or_create(
        name=target,
        defaults={'private': source_list.private})
    if created and target_list.private:
        for member in source_list.members.all():
            target_list.members.add(member)
    # create directory if needed
    path = os.path.join(settings.ARCHIVE_DIR, target)
    if not os.path.exists(path):
        os.mkdir(path)
        os.chmod(path, 0o2777)
    # move message files
    for msg in source_list.message_set.all():
        _ = len(msg.pymsg)  # evaluate msg.pymsg
        source_path = msg.get_file_path()
        old_url = msg.get_absolute_url()
        # get new hashcode
        mw = MessageWrapper(message=msg.pymsg, listname=target)
        hashcode = mw.get_hash()
        msg.hashcode = hashcode
        msg.email_list = target_list
        msg.save()
        # move file on disk
        target_path = msg.get_file_path()
        shutil.move(source_path, target_path)
        # create redirect
        new_url = msg.get_absolute_url()
        Redirect.objects.create(old=old_url, new=new_url)
