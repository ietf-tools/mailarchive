from builtins import input

import datetime
import email
import json
import logging
import mailbox
import os
import re
import requests
import shutil
import subprocess
import sys
from collections import defaultdict

import mailmanclient
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from mlarchive.archive.models import (EmailList, Subscriber, Redirect, UserEmail, MailmanMember,
    User, Message)
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

    today_utc = datetime.datetime.now(datetime.UTC).date()
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


def get_membership(quiet=False):
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
        mailman_members = [m.email for m in mailman_list.members]
        existing_members = plist.mailmanmember_set.values_list('address', flat=True)
        # handle new members
        for address in set(mailman_members) - set(existing_members):
            MailmanMember.objects.create(email_list=plist, address=address)
            try:
                user_email = UserEmail.objects.get(address=address)
            except UserEmail.DoesNotExist:
                continue
            plist.members.add(user_email.user)
            has_changed = True
        # handle deleted members
        for addresss in set(existing_members) - set(mailman_members):
            # do not delete unsubscribed members
            # one time subscribers retain access to the archives
            pass

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
    yesterday = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
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


def get_known_emails(email):
    '''Calls Datatracker API to retrieve all known emails related to given email'''
    url = settings.DATATRACKER_EMAIL_RELATED_URL.format(email=email)
    headers = {
        "X-API-KEY": settings.DATATRACKER_EMAIL_RELATED_API_KEY,
        "Accept": "application/json",
    }
    response = requests.get(url, headers=headers, timeout=settings.DEFAULT_REQUESTS_TIMEOUT)
    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f'get_known_emails(): cannot decode response {e}')
        if 'addresses' in data:
            return data['addresses']
        else:
            logger.warning('get_known_emails(): No addresses in response')
    else:
        logger.warning(f'get_known_emails(): Received unexpected status code {response.status_code}')

    return []

# -------------------------------------------------------
# Delete functions below after migrating
# -------------------------------------------------------

def init_private_list_members():
    # init mailmanmember for all private lists in mailman
    init_mailmanmember()

    # check / migrate users
    # per Robert, do not attempt to convert these, rely on
    # user requests if needed to provide access to old lists
    # init_check_users()

    # set missing emails
    init_set_user_email()

    # derive mailmanmember for old private lists
    init_derived_mailmanmember()


def init_mailmanmember():
    '''Get members for all private lists from mailman and
    create MailmanMember objects'''
    client = mailmanclient.Client(
        settings.MAILMAN_API_URL,
        settings.MAILMAN_API_USER,
        settings.MAILMAN_API_PASSWORD,
        request_hooks=[add_cloudflare_credentials])

    private_lists = get_mailman_lists(private=True)
    fqdn_map = get_fqdn_map()
    for plist in private_lists:
        if plist.name not in fqdn_map:
            logger.warning("Can't find fqdn for list: {}".format(plist.name))
            continue
        fqdn = plist.name + '@' + fqdn_map[plist.name]
        mailman_list = client.get_list(fqdn)
        mailman_members = [m.email for m in mailman_list.members]
        existing_members = plist.mailmanmember_set.values_list('address', flat=True)
        # handle new members
        for address in set(mailman_members) - set(existing_members):
            MailmanMember.objects.create(email_list=plist, address=address)


def init_check_users():
    '''For all Users, check that User.username is an email in Datatracker.
    If not, it was a User.username from Datatracker. Find the primary email
    for this Datatracker account and change username,email to that.
    '''
    count = 0
    for user in User.objects.all():
        # check if user.username is a known datatracker email
        logger.info(f'checking {user.username}')
        is_valid_email = True
        try:
            validate_email(user.username)
        except ValidationError:
            is_valid_email = False
            logger.info(f'{user.username} is not a valid email. Not looking up.')

        if is_valid_email:
            is_known_email = lookup_user(user.username) is not None
        else:
            is_known_email = False

        if not is_known_email:
            count = count + 1
            email = username_to_email(username=user.username)
            if not email:
                logger.warn(f'init_check_users: no email found for {user.username}')
                # logger.info(f'deleting user {user.username}')
                # user.delete()
                continue
            logger.info(f'Found non-email user.username. Converting {user.username} to {email}')
            logger.info(f'{user.username}=>{email}')
            new_user, created = User.objects.get_or_create(username=email, defaults={'email': email})
            emaillists = user.emaillist_set.all()
            new_user.emaillist_set.add(*emaillists)
            # assert user.last_login is None      # confirm never logged in
            # logger.info(f'deleting user {user.username}')
            # user.delete()
    logger.info(f'{count} changed')


def init_set_user_email():
    '''Old Users created by get_subscribers didn't get email set. Set from
    username if it is a valid email'''
    for user in User.objects.filter(email=''):
        try:
            validate_email(user.username)
        except ValidationError:
            continue
        user.email = user.username
        user.save()


def init_derived_mailmanmember():
    '''For private lists no longer managed by mailman (they have been closed / deleted)
    create MailmanMember objects for all current member relations. This preserves the
    list membership going forward in the archive with the new setup. This way if
    someone had subscribed to an old list with an email Datatracker didn't know about,
    now when they add that email to Datatracker the member relationship will be created
    and access granted.
    '''
    mailman_lists = get_mailman_lists(private=True)
    pks = [x.pk for x in mailman_lists]
    non_mailman_lists = EmailList.objects.filter(private=True).exclude(pk__in=pks)
    for elist in non_mailman_lists:
        for member in elist.members.all():
            MailmanMember.objects.create(email_list=elist, address=member.username)


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
        user = output['person.person'][person_ids[0]]['user']
        if user == 'None':
            return None
        username = user['username']
    except (TypeError, LookupError) as error:
        logger.error(f'lookup_user json response: {output}')
        logger.error(str(error))
        return None

    if username_map is None:
        username_map = {}

    username_map[address] = username
    cache.set('username_map', username_map, timeout=None)

    return username


def username_to_email(username):
    apikey = settings.DATATRACKER_PERSON_ENDPOINT_API_KEY
    url = settings.DATATRACKER_PERSON_ENDPOINT
    data = {'apikey': apikey, '_expand': 'email_set', 'user__username': username}

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
            logger.warning(f'username_to_email failed for {username}')
            return None
        email_set = output["person.person"][person_ids[0]]["email_set"]
        found_email = next(
            (email for email, details in email_set.items() if details.get("primary")), None
        )
        if not found_email:
            # try active
            found_email = next(
                (email for email, details in email_set.items() if details.get("active")), None
            )
        if not found_email:
            # settle for inactive
            found_email = next(
                (email for email, details in email_set.items()), None
            )

    except (TypeError, LookupError) as error:
        logger.error(str(error))
        return None

    return found_email


def get_mbox_updates(queryset):
    """Returns the list of mbox files to rebuild, identified by the tuple
    (month, year, list id)
    """
    results = set()
    for message in queryset:
        results.add((message.date.month, message.date.year, message.email_list.pk))
    return list(results)


def remove_selected(user_id):
    user = User.objects.get(id=user_id)
    queryset = Message.objects.filter(spam_score=settings.SPAM_SCORE_TO_REMOVE)
    for message in queryset:
        logger.info('User %s removed message [list=%s,hash=%s,msgid=%s,pk=%s]' %
                    (user, message.email_list, message.hashcode, message.msgid, message.pk))
    mbox_updates = get_mbox_updates(queryset)
    queryset.delete()
    for file in mbox_updates:
        elist = EmailList.objects.get(pk=file[2])
        create_mbox_file(file[0], file[1], elist)


def mark_not_spam(message_ids):
    # queryset.update() doesn't call save() which means the index doesn't get updated
    # via RealtimeSingalProcessor, need to loop through and call save()
    for message in Message.objects.filter(id__in=message_ids):
        message.spam_score = settings.SPAM_SCORE_NOT_SPAM
        message.save()
