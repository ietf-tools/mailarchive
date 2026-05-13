from builtins import input

import datetime
import email
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
import logging
import mailbox
import os
import re
import requests
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import mailmanclient
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from mlarchive.archive.models import (EmailList, Subscriber, Redirect, UserEmail, MailmanMember,
    User, Message)
from mlarchive.archive.mail import MessageWrapper, archive_message
from mlarchive.archive.storage_utils import retrieve_bytes
from mlarchive.blobdb.models import Blob


logger = logging.getLogger(__name__)
THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
LIST_LISTS_PATTERN = re.compile(r'\s*([\w\-]*) - (.*)$')
MAILMAN_LISTID_PATTERN = re.compile(r'(.*)\.(ietf|irtf|iab|iesg|rfc-editor)\.org')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.debug('%s took %.3fs', func.__qualname__, elapsed)
        return result
    return wrapper


def build_blob_batch(messages):
    """Read message content from NFS and return a list of Blob objects ready for bulk_create.

    Skips messages whose files are missing. The returned list may be shorter than
    the input if any files are not found.
    """
    from mlarchive.blobdb.models import Blob

    def bucket_for(message):
        return 'ml-messages-private' if message.email_list.private else 'ml-messages'

    batch = []
    for message in messages:
        try:
            with open(message.get_file_path(), 'rb') as f:
                content = f.read()
        except FileNotFoundError:
            logger.warning('build_blob_batch: missing file for pk=%d path=%s', message.pk, message.get_file_path())
            continue
        batch.append(Blob(
            name=message.get_blob_name(),
            bucket=bucket_for(message),
            content=content,
            content_type='message/rfc822',
        ))
    return batch


def replicate_blob_direct(blob):
    """Replicate a Blob using content already in memory, skipping the SQL re-fetch."""
    from mlarchive.blobdb.replication import (
        destination_storage_for, replication_enabled, ReplicationError, SimpleMetadataFile
    )
    if not replication_enabled(blob.bucket):
        return
    file_with_metadata = SimpleMetadataFile(file=BytesIO(bytes(blob.content)))
    file_with_metadata.content_type = blob.content_type
    file_with_metadata.custom_metadata = {
        'sha384': blob.checksum,
        'mtime': (blob.mtime or blob.modified).isoformat(),
    }
    try:
        destination_storage_for(blob.bucket).save(blob.name, file_with_metadata)
    except Exception as e:
        raise ReplicationError from e


def replicate_batch(blobs, max_workers=50):
    """Replicate a list of Blob objects to R2 using a thread pool.

    Returns a list of (blob, exception) tuples for any failures.
    """
    from mlarchive.blobdb.replication import ReplicationError

    failures = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(replicate_blob_direct, blob): blob for blob in blobs}
        for future in as_completed(futures):
            try:
                future.result()
            except ReplicationError as e:
                blob = futures[future]
                logger.warning('replicate_batch: failed %s:%s: %s', blob.bucket, blob.name, e)
                failures.append((blob, e))
    return failures


_NAV_SQL = """
SELECT
    m.id,
    pl.hashcode  AS prev_list_hc,  pl.list_name  AS prev_list_ln,
    nl.hashcode  AS next_list_hc,  nl.list_name  AS next_list_ln,
    COALESCE(pts.hashcode, pte.hashcode) AS prev_thread_hc,
    COALESCE(pts.list_name, pte.list_name) AS prev_thread_ln,
    COALESCE(nts.hashcode, nte.hashcode) AS next_thread_hc,
    COALESCE(nts.list_name, nte.list_name) AS next_thread_ln
FROM archive_message m
JOIN archive_thread mt ON mt.id = m.thread_id
LEFT JOIN LATERAL (
    SELECT p.hashcode, el.name AS list_name
    FROM archive_message p JOIN archive_emaillist el ON el.id = p.email_list_id
    WHERE p.email_list_id = m.email_list_id AND p.date < m.date
    ORDER BY p.date DESC LIMIT 1
) pl ON true
LEFT JOIN LATERAL (
    SELECT n.hashcode, el.name AS list_name
    FROM archive_message n JOIN archive_emaillist el ON el.id = n.email_list_id
    WHERE n.email_list_id = m.email_list_id AND n.date > m.date
    ORDER BY n.date ASC LIMIT 1
) nl ON true
LEFT JOIN LATERAL (
    SELECT p.hashcode, el.name AS list_name
    FROM archive_message p JOIN archive_emaillist el ON el.id = p.email_list_id
    WHERE p.thread_id = m.thread_id AND p.thread_order < m.thread_order
    ORDER BY p.thread_order DESC LIMIT 1
) pts ON true
LEFT JOIN LATERAL (
    SELECT p.hashcode, el.name AS list_name
    FROM archive_thread t
    JOIN archive_message p ON p.thread_id = t.id
    JOIN archive_emaillist el ON el.id = p.email_list_id
    WHERE t.email_list_id = m.email_list_id AND t.date < mt.date
    ORDER BY t.date DESC, p.thread_order ASC LIMIT 1
) pte ON true
LEFT JOIN LATERAL (
    SELECT n.hashcode, el.name AS list_name
    FROM archive_message n JOIN archive_emaillist el ON el.id = n.email_list_id
    WHERE n.thread_id = m.thread_id AND n.thread_order > m.thread_order
    ORDER BY n.thread_order ASC LIMIT 1
) nts ON true
LEFT JOIN LATERAL (
    SELECT n.hashcode, el.name AS list_name
    FROM archive_thread t
    JOIN archive_message n ON n.thread_id = t.id
    JOIN archive_emaillist el ON el.id = n.email_list_id
    WHERE t.email_list_id = m.email_list_id AND t.date > mt.date
    ORDER BY t.date ASC, n.thread_order ASC LIMIT 1
) nte ON true
WHERE m.id = ANY(%s)
"""


def _nav_url(hashcode, list_name):
    if hashcode is None:
        return ''
    return reverse('archive_detail', kwargs={'list_name': list_name, 'id': hashcode.rstrip('=')})


def fetch_nav_for_batch(messages):
    """Return nav URLs for all messages in one SQL query.

    Returns {pk: {'previous_in_list': url, 'next_in_list': url,
                  'previous_in_thread': url, 'next_in_thread': url}}
    """
    pks = [m.pk for m in messages]
    if not pks:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(_NAV_SQL, [pks])
        rows = cursor.fetchall()
    result = {}
    for pk, pl_hc, pl_ln, nl_hc, nl_ln, pt_hc, pt_ln, nt_hc, nt_ln in rows:
        result[pk] = {
            'previous_in_list': _nav_url(pl_hc, pl_ln),
            'next_in_list': _nav_url(nl_hc, nl_ln),
            'previous_in_thread': _nav_url(pt_hc, pt_ln),
            'next_in_thread': _nav_url(nt_hc, nt_ln),
        }
    return result


def build_json_blob_batch(messages):
    """Build JSON blob objects for public messages, ready for bulk_create."""
    public = [m for m in messages if not m.email_list.private]
    if not public:
        return []
    nav_map = fetch_nav_for_batch(public)
    batch = []
    for message in public:
        batch.append(Blob(
            name=message.get_blob_name(),
            bucket='ml-messages-json',
            content=message.as_json(nav=nav_map.get(message.pk)).encode('utf-8'),
            content_type='application/json',
        ))
    return batch


def migrate_messages_to_blobdb(messages, max_workers=50):
    """Migrate a batch of Messages to blobdb and replicate to R2.

    Steps (each timed):
      1. build_blob_batch       — read raw message content from NFS
      2. bulk_create messages   — insert into blobdb
      3. replicate messages     — upload to R2 via thread pool
      4. build_json_blob_batch  — serialise JSON for public messages
      5. bulk_create json       — insert into blobdb
      6. replicate json         — upload to R2 via thread pool
    """
    n = len(messages)
    all_failures = []

    t0 = time.perf_counter()
    blobs = build_blob_batch(messages)
    logger.info('migrate step 1/6 build_blob_batch: %.3fs, %d/%d blobs built', time.perf_counter() - t0, len(blobs), n)

    t1 = time.perf_counter()
    Blob.objects.bulk_create(blobs, ignore_conflicts=True)
    logger.info('migrate step 2/6 bulk_create messages: %.3fs, %d blobs', time.perf_counter() - t1, len(blobs))

    t2 = time.perf_counter()
    failures = replicate_batch(blobs, max_workers=max_workers)
    all_failures.extend(failures)
    logger.info('migrate step 3/6 replicate messages: %.3fs, %d failures', time.perf_counter() - t2, len(failures))

    t3 = time.perf_counter()
    json_blobs = build_json_blob_batch(messages)
    logger.info('migrate step 4/6 build_json_blob_batch: %.3fs, %d blobs', time.perf_counter() - t3, len(json_blobs))

    t4 = time.perf_counter()
    Blob.objects.bulk_create(json_blobs, ignore_conflicts=True)
    logger.info('migrate step 5/6 bulk_create json: %.3fs, %d blobs', time.perf_counter() - t4, len(json_blobs))

    t5 = time.perf_counter()
    failures = replicate_batch(json_blobs, max_workers=max_workers)
    all_failures.extend(failures)
    logger.info('migrate step 6/6 replicate json: %.3fs, %d failures', time.perf_counter() - t5, len(failures))

    return all_failures


def is_mailman_footer(part):
    """Check if a message part is a Mailman footer.

    Mailman footers are identified by:
    - Content type is text/plain
    - After removing leading whitespace, starts with "___"
    - Contains the text "listinfo"

    Args:
        part: An email message part

    Returns:
        bool: True if this is a Mailman footer, False otherwise
    """
    # Check content type
    if part.get_content_type() != 'text/plain':
        return False

    # Get the payload
    payload = part.get_payload(decode=True)
    if payload is None:
        return False

    # Decode to string if bytes
    if isinstance(payload, bytes):
        try:
            payload = payload.decode('utf-8', errors='ignore')
        except Exception:
            return False

    # Check if starts with ___ after stripping leading whitespace
    stripped = payload.lstrip()
    if not stripped.startswith('___'):
        return False

    # Check if contains "listinfo"
    if 'listinfo' not in payload:
        return False

    return True


# Matches the Mailman footer separator (10+ underscores on its own line)
# so it can be stripped before payload comparison.
_MAILMAN_FOOTER_SEP_RE = re.compile(rb'\n_{10,}\n')


def _normalized_payload(part):
    """Return decoded payload with CRLF normalised to LF and inline Mailman footer stripped."""
    data = part.get_payload(decode=True)
    if data is None:
        return b""
    data = data.replace(b"\r\n", b"\n")
    m = _MAILMAN_FOOTER_SEP_RE.search(data)
    if m:
        data = data[:m.start()]
    return data.strip()


def is_duplicate_message(msg1, msg2):
    """Check if two email.message.EmailMessage objects are duplicates.

    Messages are considered duplicates if they have the same Message-ID
    and the same decoded content. Payloads are decoded before comparison so
    that different Content-Transfer-Encoding values (e.g. base64 vs
    quoted-printable) do not cause identical content to appear distinct.
    Line endings are normalised (CRLF → LF) so that messages that differ
    only in \r\n vs \n conventions compare equal. Headers like Received,
    which commonly differ between duplicate submissions, are ignored.
    """
    msgid1 = msg1.get('Message-ID')
    msgid2 = msg2.get('Message-ID')

    if msgid1 != msgid2:
        return False

    # If Message-IDs match, compare the actual message content
    # Get the payload (body) of both messages
    if msg1.is_multipart() and msg2.is_multipart():
        # For multipart messages, compare all non-container parts
        # walk() returns all message components including multipart containers,
        # so we need to skip the container parts and only compare leaf parts
        # Also exclude Mailman footers from comparison
        parts1 = [part for part in msg1.walk()
                  if not part.is_multipart() and not is_mailman_footer(part)]
        parts2 = [part for part in msg2.walk()
                  if not part.is_multipart() and not is_mailman_footer(part)]

        if len(parts1) != len(parts2):
            return False

        for part1, part2 in zip(parts1, parts2):
            if _normalized_payload(part1) != _normalized_payload(part2):
                return False
        return True
    elif not msg1.is_multipart() and not msg2.is_multipart():
        return _normalized_payload(msg1) == _normalized_payload(msg2)
    else:
        return False


def purge_confirmed_dupes(listname=None, dry_run=False, exitfirst=False):
    """Walk through all email lists and purge confirmed duplicate messages.

    For each email list, checks the _dupes directory for messages that are
    confirmed duplicates of messages already in the archive. If a message in
    _dupes has the same Message-ID and content as an archived message, the
    duplicate file is removed and the action is logged.

    Args:
        listname: Optional name of a specific list to process. If None, processes all lists.
        dry_run: If True, only report what would be done without actually removing files.
        exitfirst: If True, exit the function on first failure (logger.warning).
    """
    removed_count = 0
    error_count = 0

    if dry_run:
        logger.info('DRY RUN MODE: No files will be removed')

    if listname:
        try:
            email_lists = [EmailList.objects.get(name=listname)]
        except EmailList.DoesNotExist:
            logger.error(f'Email list not found: {listname}')
            return {'removed': 0, 'errors': 1}
    else:
        email_lists = EmailList.objects.all()

    for elist in email_lists:
        dupes_dir = os.path.join(settings.ARCHIVE_DIR, elist.name, '_dupes')

        if not os.path.isdir(dupes_dir):
            continue

        logger.info(f'Processing _dupes directory for list: {elist.name}')

        for filename in os.listdir(dupes_dir):
            dupe_file_path = os.path.join(dupes_dir, filename)

            if not os.path.isfile(dupe_file_path):
                continue

            try:
                with open(dupe_file_path, 'rb') as f:
                    dupe_msg = email.message_from_binary_file(f)

                message_id = dupe_msg.get('Message-ID')
                if not message_id:
                    logger.warning(f'Message in _dupes has no Message-ID: {dupe_file_path}')
                    error_count += 1
                    if exitfirst:
                        return {'removed': removed_count, 'errors': error_count}
                    continue

                message_id = message_id.strip('<>')

                try:
                    archived_message = Message.objects.get(
                        email_list=elist,
                        msgid=message_id
                    )
                except Message.DoesNotExist:
                    logger.warning(f'Message-ID not found in archive, keeping in _dupes: {message_id}')
                    if exitfirst:
                        return {'removed': removed_count, 'errors': error_count}
                    continue
                except Message.MultipleObjectsReturned:
                    logger.warning(f'Multiple messages found with Message-ID: {message_id}')
                    error_count += 1
                    if exitfirst:
                        return {'removed': removed_count, 'errors': error_count}
                    continue

                archived_msg = archived_message.pymsg

                if is_duplicate_message(dupe_msg, archived_msg):
                    if dry_run:
                        logger.info(
                            f'[DRY RUN] Would remove confirmed duplicate: list={elist.name}, '
                            f'msgid={message_id}, file={filename}'
                        )
                    else:
                        os.remove(dupe_file_path)
                        logger.info(
                            f'Removed confirmed duplicate: list={elist.name}, '
                            f'msgid={message_id}, file={filename}'
                        )
                    removed_count += 1
                else:
                    logger.warning(
                        f'Message-ID matches but content differs, keeping in _dupes: '
                        f'path={dupe_file_path}, list={elist.name}, msgid={message_id}'
                    )
                    if exitfirst:
                        return {'removed': removed_count, 'errors': error_count}

            except Exception as e:
                logger.error(f'Error processing dupe file {dupe_file_path}: {e}')
                error_count += 1
                continue

    if dry_run:
        logger.info(
            f'Purge completed (DRY RUN): {removed_count} duplicates would be removed, '
            f'{error_count} errors encountered'
        )
    else:
        logger.info(
            f'Purge completed: {removed_count} duplicates removed, {error_count} errors encountered'
        )
    return {'removed': removed_count, 'errors': error_count}


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
    # private lists should not have mbox files in rsync
    if elist.private:
        return
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
    '''Purge messages older than 90 days from incoming bucket'''
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=90)
    blobs = Blob.objects.filter(bucket='ml-messages-incoming', modified__lt=cutoff_date)
    for blob in blobs:
        blob.delete()


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
        if not elist.private:
            create_mbox_file(file[0], file[1], elist)


def mark_not_spam(message_ids):
    # queryset.update() doesn't call save() which means the index doesn't get updated
    # via RealtimeSingalProcessor, need to loop through and call save()
    for message in Message.objects.filter(id__in=message_ids):
        message.spam_score = settings.SPAM_SCORE_NOT_SPAM
        message.save()


def import_message_blob(bucket, name):
    name_pattern = r"(?P<list_name>.+)\.(?P<visibility>private|public)\.(?P<hex_id>[a-f0-9]{16})$"
    match = re.match(name_pattern, name)
    if not match:
        logger.error(f'Unrecognized blob name format: {name}')
        return
    message_bytes = retrieve_bytes(bucket, name)
    if message_bytes:
        groups = match.groupdict()
        list_name = groups['list_name']
        is_private = groups['visibility'] == 'private'
        status = archive_message(
            data=message_bytes,
            listname=list_name,
            private=is_private)
        logger.info(f'Archive message status: {name} {status}')


def create_cf_worker_templates():
    """Create message template for Cloudflare worker. Here we are mainly mapping django template
    varaibles to cloudflare worker mustache variables"""
    from mlarchive import __version__, __patch__

    path = Path(settings.CF_WORKER_TEMPLATE_DIR, 'message-detail.html')
    path.parent.mkdir(parents=True, exist_ok=True)
    context = {}
    context['server_mode'] = 'production'
    context['queryid'] = None  # query based navigation turned off in generic template
    # context['static_mode_enabled']  # provided by context processor
    # pass request to enable context processors
    msg = {}
    msg['subject'] = '{{ subject }}'
    msg['get_date_index_url'] = '{{ date_index_url }}'
    msg['get_thread_index_url'] = '{{ thread_index_url }}'
    msg['get_static_date_index_url'] = '{{ static_date_index_url }}'
    msg['get_static_thread_index_url'] = '{{ static_thread_index_url }}'
    msg['get_thread_snippet'] = '{{{ thread_snippet }}}'
    msg['get_body_html'] = '{{{ body }}}'
    context['msg'] = msg
    context['previous_in_list'] = {'get_absolute_url': '{{ previous_in_list }}'}
    context['next_in_list'] = {'get_absolute_url': '{{ next_in_list }}'}
    context['previous_in_thread'] = {'get_absolute_url': '{{ previous_in_thread }}'}
    context['next_in_thread'] = {'get_absolute_url': '{{ next_in_thread }}'}
    context['version_num'] = __version__ + __patch__
    request = RequestFactory().get('/')
    request.user = AnonymousUser()
    html = render_to_string('archive/detail.html', context, request=request)
    path.write_text(html, encoding='utf-8')


def audit_blobdb():
    for elist in EmailList.objects.order_by('name'):
        if elist.private:
            bucket = 'ml-messages-private'
        else:
            bucket = 'ml-messages'
        messages = Message.objects.filter(email_list=elist)
        blobs = Blob.objects.filter(bucket=bucket, name__startswith=f'{elist.name}/')
        if messages.count() != blobs.count():
            print(f'{elist.name}    messages:{messages.count()}  blobs:{blobs.count()}')
            message_hashes = set([x.hashcode.strip('=') for x in messages])
            blob_hashes = set([x.name.split('/')[1] for x in blobs])
            print(blob_hashes - message_hashes)
