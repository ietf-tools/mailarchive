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
from collections import Counter, defaultdict
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

from mlarchive.archive.models import (EmailList, Subscriber, Redirect, MailmanMember,
    User, Message)
from mlarchive.archive.mail import MessageWrapper, archive_message
from mlarchive.archive.storage import (DriftReport, RECONCILE_MAX_MISSING_REPAIRS,
    reconcile_bucket)
from mlarchive.archive.storage_utils import (retrieve_bytes, store_bytes, exists_in_storage,
    remove_from_storage, list_names, get_metadata, find_by_checksum)
from mlarchive.archive.inspectors import is_no_archive


logger = logging.getLogger(__name__)
THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
LIST_LISTS_PATTERN = re.compile(r'\s*([\w\-]*) - (.*)$')
MAILMAN_LISTID_PATTERN = re.compile(r'(.*)\.(ietf|irtf|iab|iesg|rfc-editor)\.org')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


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


# Mailman appends a footer below a separator line of underscores. Both generations use
# the separator, the block below it differs:
#   MM2: "<name> mailing list" / "<list>@<host>" / "<...>/mailman/listinfo/<list>"
#   MM3: "<name> mailing list -- <addr>" / "To unsubscribe send an email to <list>-leave@<domain>"
_MAILMAN_FOOTER_SEP_RE = re.compile(rb'(?m)^_{10,}[ \t]*$')

# a footer is a handful of short lines. A larger block below a separator is real content
# that happens to follow a rule of underscores, which is common in ordinary mail
_MAILMAN_FOOTER_MAX_LINES = 6
_MAILMAN_FOOTER_MAX_BYTES = 500

# wording that identifies the block below the separator as a Mailman footer
_MAILMAN_FOOTER_SIGNATURES = (
    b'/listinfo/',                          # MM2 list info URL
    b'/mailman/options/',                   # MM2 options URL
    b'mailing list --',                     # MM3 first line
    b'-leave@',                             # MM3 unsubscribe address
    b'To unsubscribe send an email to',     # MM3 second line
)

# values in List-* headers are wrapped in angle brackets, possibly several per header
_LIST_HEADER_VALUE_RE = re.compile(r'<([^>]+)>')


def get_footer_tokens(message):
    """Returns byte strings taken from a message's List-* headers that Mailman writes
    into its footer, ie. the list posting address and the unsubscribe address or URL.

    Matching on these identifies the footer of the list this message was sent to, so
    footer detection does not depend on the wording of a particular Mailman version.
    """
    tokens = []
    if message is None:
        return tokens
    for header in ('List-Post', 'List-Unsubscribe', 'List-Subscribe'):
        value = message.get(header, '')
        if not value:
            continue
        for item in _LIST_HEADER_VALUE_RE.findall(str(value)):
            item = item.strip()
            if item.lower().startswith('mailto:'):
                item = item[len('mailto:'):]
            item = item.split('?')[0].strip()
            # anything shorter is not distinctive enough to identify a footer
            if len(item) >= 8:
                tokens.append(item.encode('utf-8', errors='ignore'))
    return tokens


def strip_mailman_footer(data, message=None):
    """Returns data with a trailing Mailman footer removed, or data unchanged.

    Only the last separator line is considered, and the block below it is removed only
    if it is small enough to be a footer and is identifiable as one, either by the
    wording Mailman 2 or 3 uses or by an address taken from the message's List-*
    headers. Everything else is left alone. Removing real content would make two
    different messages compare equal in is_duplicate_message(), which drops a message
    that should have been archived, so the bias here is to strip nothing when unsure.

    Args:
        data: the decoded payload, as bytes, with line endings already normalised
        message: the message the payload came from, used for its List-* headers

    Returns:
        bytes: data, with any trailing Mailman footer removed
    """
    matches = list(_MAILMAN_FOOTER_SEP_RE.finditer(data))
    if not matches:
        return data

    separator = matches[-1]
    tail = data[separator.end():]
    if (len(tail) > _MAILMAN_FOOTER_MAX_BYTES
            or tail.count(b'\n') > _MAILMAN_FOOTER_MAX_LINES):
        return data

    if not (any(signature in tail for signature in _MAILMAN_FOOTER_SIGNATURES)
            or any(token in tail for token in get_footer_tokens(message))):
        return data

    return data[:separator.start()]


def is_mailman_footer(part, message=None):
    """Check if a message part holds nothing but a Mailman footer.

    A multipart message may carry the footer as a part of its own, which is dropped
    before comparing content, see is_duplicate_message(). Defined in terms of
    strip_mailman_footer() so both share one definition of what a footer is.

    Args:
        part: An email message part
        message: the message the part came from, used for its List-* headers

    Returns:
        bool: True if this part is a Mailman footer, False otherwise
    """
    if part.get_content_type() != 'text/plain':
        return False

    data = part.get_payload(decode=True)
    if data is None:
        return False
    data = data.replace(b"\r\n", b"\n").strip()
    if not data:
        return False

    return strip_mailman_footer(data, message).strip() == b''


def _normalized_payload(part, message=None):
    """Return decoded payload with CRLF normalised to LF and a trailing Mailman footer
    stripped. Trailing whitespace only is trimmed, leading whitespace is content.
    """
    data = part.get_payload(decode=True)
    if data is None:
        return b""
    data = data.replace(b"\r\n", b"\n")
    return strip_mailman_footer(data, message).rstrip()


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
                  if not part.is_multipart() and not is_mailman_footer(part, msg1)]
        parts2 = [part for part in msg2.walk()
                  if not part.is_multipart() and not is_mailman_footer(part, msg2)]

        if len(parts1) != len(parts2):
            return False

        for part1, part2 in zip(parts1, parts2):
            if _normalized_payload(part1, msg1) != _normalized_payload(part2, msg2):
                return False
        return True
    elif not msg1.is_multipart() and not msg2.is_multipart():
        return _normalized_payload(msg1, msg1) == _normalized_payload(msg2, msg2)
    else:
        return False


def _build_removed_message_ids(list_name):
    """Return a dict mapping Message-ID to file path for all messages in list/_removed/."""
    removed_message_ids = {}
    removed_dir = os.path.join(settings.ARCHIVE_DIR, list_name, '_removed')
    if not os.path.isdir(removed_dir):
        return removed_message_ids
    for filename in os.listdir(removed_dir):
        file_path = os.path.join(removed_dir, filename)
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, 'rb') as f:
                msg = email.message_from_binary_file(f)
            msgid = msg.get('Message-ID')
            if msgid:
                removed_message_ids[msgid.strip('<>')] = file_path
        except Exception:
            pass
    return removed_message_ids


def _get_removed_message(message_id, removed_message_ids):
    """Return the parsed email object for message_id from _removed, or None if not found."""
    if message_id not in removed_message_ids:
        return None
    try:
        with open(removed_message_ids[message_id], 'rb') as f:
            return email.message_from_binary_file(f)
    except Exception:
        return None


def purge_confirmed_dupes(listname=None, dry_run=False, exitfirst=False, verbosity=1):
    """Walk through all email lists and purge confirmed duplicate messages.

    For each email list, checks the _dupes directory for messages that are
    confirmed duplicates of messages already in the archive. If a message in
    _dupes has the same Message-ID and content as an archived message, the
    duplicate file is removed and the action is logged.

    Args:
        listname: Optional name of a specific list to process. If None, processes all lists.
        dry_run: If True, only report what would be done without actually removing files.
        exitfirst: If True, exit the function on first failure (logger.warning).
        verbosity: Controls logging output level (0-3). 0=totals only, 1=+list names and
            errors, 2=+messages when not removing, 3=+messages when removing.
    """
    removed_count = 0
    error_count = 0

    if dry_run and verbosity >= 1:
        logger.info('DRY RUN MODE: No files will be removed')

    if listname:
        try:
            email_lists = [EmailList.objects.get(name=listname)]
        except EmailList.DoesNotExist:
            if verbosity >= 1:
                logger.error(f'Email list not found: {listname}')
            return {'removed': 0, 'errors': 1}
    else:
        email_lists = EmailList.objects.all().order_by('name')

    for elist in email_lists:
        dupes_dir = os.path.join(settings.ARCHIVE_DIR, elist.name, '_dupes')

        if not os.path.isdir(dupes_dir):
            continue

        if verbosity >= 1:
            logger.info(f'Processing _dupes directory for list: {elist.name}')

        removed_message_ids = None  # lazy: built on first Message.DoesNotExist

        for filename in os.listdir(dupes_dir):
            dupe_file_path = os.path.join(dupes_dir, filename)

            if not os.path.isfile(dupe_file_path):
                continue

            try:
                with open(dupe_file_path, 'rb') as f:
                    dupe_msg = email.message_from_binary_file(f)

                message_id = dupe_msg.get('Message-ID')
                if not message_id:
                    if verbosity >= 2:
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
                    archived_msg = archived_message.pymsg
                except Message.DoesNotExist:
                    if removed_message_ids is None:
                        removed_message_ids = _build_removed_message_ids(elist.name)
                    archived_msg = _get_removed_message(message_id, removed_message_ids)
                    if archived_msg is None:
                        if verbosity >= 2:
                            logger.warning(f'Message-ID not found in archive, keeping in _dupes: {message_id}')
                        if exitfirst:
                            return {'removed': removed_count, 'errors': error_count}
                        continue
                except Message.MultipleObjectsReturned:
                    if verbosity >= 2:
                        logger.warning(f'Multiple messages found with Message-ID: {message_id}')
                    error_count += 1
                    if exitfirst:
                        return {'removed': removed_count, 'errors': error_count}
                    continue

                if is_duplicate_message(dupe_msg, archived_msg):
                    if dry_run:
                        if verbosity >= 3:
                            logger.info(
                                f'[DRY RUN] Would remove confirmed duplicate: list={elist.name}, '
                                f'msgid={message_id}, file={filename}'
                            )
                    else:
                        os.remove(dupe_file_path)
                        blob_name = os.path.join(elist.name, filename.rstrip('='))
                        if exists_in_storage('ml-messages-dupes', blob_name):
                            remove_from_storage('ml-messages-dupes', blob_name)
                        if verbosity >= 3:
                            logger.info(
                                f'Removed confirmed duplicate: list={elist.name}, '
                                f'msgid={message_id}, file={filename}'
                            )
                    removed_count += 1
                else:
                    if verbosity >= 2:
                        logger.warning(
                            f'Message-ID matches but content differs, keeping in _dupes: '
                            f'path={dupe_file_path}, list={elist.name}, msgid={message_id}'
                        )
                    if exitfirst:
                        return {'removed': removed_count, 'errors': error_count}

            except Exception as e:
                if verbosity >= 1:
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


def load_hidden_messages(directory, listname=None, verbosity=1):
    """Load message files from each list's _[directory]/ directory into blob storage.

    Walks settings.ARCHIVE_DIR/[listname]/_[directory]/ for every directory found in
    settings.ARCHIVE_DIR (or a single list if listname is given) and stores each file's
    contents in the 'ml-messages-[directory]' bucket under the blob name
    '[listname]/[hashcode]'. Archive directories are used rather than EmailList records
    because some archive directories have no corresponding EmailList object. The
    filenames on disk are the padded hashcodes, so the blob name is derived by
    stripping trailing '=' padding to match Message.get_blob_name().

    Blobs that already exist in the bucket are skipped, so the task is safe to re-run.

    Args:
        directory: Name of the hidden subdirectory (without leading '_'), e.g. 'removed'
            or 'dupes'. Selects both the NFS source directory and the target bucket.
            Raises ValueError if 'ml-messages-[directory]' is not a configured bucket.
        listname: Optional name of a specific list to process. If None, processes all
            archive directories.
        verbosity: Controls logging output level (0-3). 0=totals only, 1=+list names and
            errors, 2=+skipped (already present), 3=+each loaded file.

    Returns:
        dict with 'loaded', 'skipped', and 'errors' counts.
    """
    subdir = f'_{directory}'
    bucket = f'ml-messages-{directory}'
    if bucket not in settings.ARTIFACT_STORAGE_NAMES:
        raise ValueError(
            f'No storage bucket configured for directory {directory!r} '
            f'(expected {bucket} in settings.ARTIFACT_STORAGE_NAMES)'
        )
    loaded_count = 0
    skipped_count = 0
    error_count = 0

    if listname:
        list_names = [listname]
    elif os.path.isdir(settings.ARCHIVE_DIR):
        list_names = sorted(
            entry.name for entry in os.scandir(settings.ARCHIVE_DIR) if entry.is_dir()
        )
    else:
        logger.error(f'Archive directory does not exist: {settings.ARCHIVE_DIR}')
        list_names = []

    for name in list_names:
        source_dir = os.path.join(settings.ARCHIVE_DIR, name, subdir)

        if not os.path.isdir(source_dir):
            continue

        if verbosity >= 1:
            logger.info(f'Processing {subdir} directory for list: {name}')

        for filename in os.listdir(source_dir):
            file_path = os.path.join(source_dir, filename)

            if not os.path.isfile(file_path):
                continue

            blob_name = os.path.join(name, filename).rstrip('=')

            try:
                if exists_in_storage(bucket, blob_name):
                    if verbosity >= 2:
                        logger.info(f'Already in {bucket}, skipping: {blob_name}')
                    skipped_count += 1
                    continue

                with open(file_path, 'rb') as f:
                    content = f.read()
                mtime = datetime.datetime.fromtimestamp(
                    os.path.getmtime(file_path), tz=datetime.UTC)
                store_bytes(
                    bucket,
                    blob_name,
                    content,
                    content_type='message/rfc822',
                    mtime=mtime,
                )
                if verbosity >= 3:
                    logger.info(f'Loaded hidden message: bucket={bucket}, blob={blob_name}')
                loaded_count += 1
            except Exception as e:
                if verbosity >= 1:
                    logger.error(f'Error loading file {file_path}: {e}')
                error_count += 1
                continue

    logger.info(
        f'load_hidden_messages ({subdir}) completed: {loaded_count} loaded, '
        f'{skipped_count} skipped, {error_count} errors'
    )
    return {'loaded': loaded_count, 'skipped': skipped_count, 'errors': error_count}


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
    """For all private lists, get membership from mailman 3 API and update
    list membership as needed.

    Initial plan was to use client.members to get all list memberships rather
    than hitting the API for every private list, but this request fails
    trying to retrieve millions of records.

    The member relations are reconciled against all recorded MailmanMembers,
    not just the newly seen addresses, so a relation that was missed on an
    earlier run gets added, including for an address that has since
    unsubscribed. An address can be known to more than one User, when someone
    changes their Datatracker primary email and OIDC creates a new User for
    them, in which case all of them get access.
    """
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
        existing_members = set(plist.mailmanmember_set.values_list('address', flat=True))
        # handle new members
        for address in set(mailman_members) - existing_members:
            MailmanMember.objects.create(email_list=plist, address=address)
        # grant access to every recorded subscriber we know a User for
        addresses = plist.mailmanmember_set.values_list('address', flat=True)
        users = list(User.objects.filter(useremail__address__in=addresses)
                                 .exclude(pk__in=plist.members.values_list('pk', flat=True))
                                 .distinct())
        if users:
            plist.members.add(*users)
            has_changed = True

        # no action is taken for deleted members, existing_members - set(mailman_members).
        # past members retain access to lists

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
        mbox.add(email.message_from_bytes(message.get_raw_message()))
    mbox.close()


def update_mbox_files():
    '''Update archive mbox files'''
    yesterday = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    month = yesterday.month
    year = yesterday.year
    for elist in EmailList.objects.filter(active=True, private=False):
        if elist.message_set.filter(date__month=month, date__year=year).count() > 0:
            create_mbox_file(month=month, year=year, elist=elist)


def is_redelivery_of_archived(content, name):
    '''Returns True if content is a redelivery of a message already archived on the
    list named by an incoming blob or file name, "{list_name}.{visibility}.{hex_id}".

    A redelivery is dropped by MessageWrapper.check_redelivery() without being stored
    anywhere, since it is a known duplicate needing no review. That leaves its incoming
    copy with nothing to match against, so purge_incoming() identifies it here instead.
    '''
    parts = name.rsplit('.', 2)
    if len(parts) != 3:
        return False
    try:
        mw = MessageWrapper.from_bytes(content, listname=parts[0])
    except Exception as e:
        logger.warning(f'is_redelivery_of_archived: cannot read message {name}: {e}')
        return False
    if mw.created_id:
        # get_msgid() minted a random id, there is no message-id to match on
        return False
    return mw.find_duplicate() is not None


def purge_incoming():
    """Purge objects older than settings.INCOMING_DAYS_TO_KEEP days from the incoming store.

    Before purging each object, verifies that its content was processed by confirming
    an object with the same sha384 digest exists in some other raw message store. The
    archived message is stored byte-for-byte, so a match in ml-messages,
    ml-messages-private, ml-messages-removed, etc. means the message is accounted for.
    The match is intentionally content-based and list-agnostic.

    Messages that requested not to be archived (NoArchiveInspector) are deliberately
    dropped without being stored anywhere, so they have no matching object; these are
    confirmed by re-checking the no-archive headers and purged. A redelivery of an
    already archived message is likewise dropped without a copy and confirmed against
    the archive. Anything else with no match is left in place and logged.

    Returns a dict of counts: purged, skipped (no match found) and errors.
    """
    kind = 'ml-messages-incoming'
    cutoff_date = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=settings.INCOMING_DAYS_TO_KEEP)
    stats = {'purged': 0, 'skipped': 0, 'errors': 0}
    for name in list(list_names(kind, modified_before=cutoff_date)):
        try:
            metadata = get_metadata(kind, name)
            if metadata is None:
                # deleted since the listing was taken
                continue

            # find an identical object in any other raw message archive store
            if find_by_checksum(metadata.sha384, exclude_kinds=(kind, 'ml-messages-json')):
                remove_from_storage(kind, name)
                stats['purged'] += 1
                continue

            content = retrieve_bytes(kind, name)

            # no stored copy: a no-archive message is dropped without being stored
            # anywhere, so confirm it asked not to be archived and purge it
            if is_no_archive(email.message_from_bytes(content)):
                remove_from_storage(kind, name)
                stats['purged'] += 1
                continue

            # no stored copy: a redelivery is also dropped without being stored
            # anywhere, so confirm it duplicates an archived message and purge it
            if is_redelivery_of_archived(content, name):
                remove_from_storage(kind, name)
                stats['purged'] += 1
                continue

            stats['skipped'] += 1
            logger.error(
                f'purge_incoming: no matching object found outside incoming store, skipping: '
                f'name={name}, sha384={metadata.sha384}'
            )
        except Exception as err:
            # the object is left in place; one bad object must not stop the run
            stats['errors'] += 1
            logger.error(f'purge_incoming: error processing {kind}:{name}: {repr(err)}')

    logger.info(f'purge_incoming: {stats}')
    return stats


def move_list(source, target):
    '''Move messages from source list to target list. Includes:
    - create the new list if it doesn't exist
    - moving files on disk
    - moving blobs, the hashcode, hence the blob name, changes with the list
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
        content = msg.get_raw_message()
        source_path = msg.get_file_path()
        source_bucket = msg.get_blob_bucket()
        source_blob_name = msg.get_blob_name()
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
        # move blob. move_object() can't be used, the name changes as well as the bucket
        store_bytes(msg.get_blob_bucket(), msg.get_blob_name(), content,
                    content_type='message/rfc822')
        remove_from_storage(source_bucket, source_blob_name)
        remove_from_storage('ml-messages-json', source_blob_name, warn_if_missing=False)
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


def audit_list_objects(elist):
    """Compare the messages of elist with the live stored objects under its prefix.

    Every Message should have an object named after it in the list's bucket, and every
    object there should belong to a Message. Returns two sets of hashcodes, as they
    appear in object names (padding stripped): those with a message but no object,
    and those with an object but no message. Either being non-empty is logged with a
    sample of the hashcodes. Nothing is repaired: a message without bytes cannot be
    reconstructed here, and an object without a message is for a person to judge.
    """
    prefix = f'{elist.name}/'
    object_hashes = {
        name[len(prefix):] for name in list_names(elist.blob_bucket, prefix=prefix)}
    message_hashes = {
        hashcode.rstrip('=')
        for hashcode in Message.objects.filter(email_list=elist)
        .values_list('hashcode', flat=True).iterator(chunk_size=5000)
    }
    only_messages = message_hashes - object_hashes
    only_objects = object_hashes - message_hashes
    if only_messages or only_objects:
        drift = DriftReport(f'list {elist.name}')
        drift.add('messages with no stored object', sorted(only_messages))
        drift.add('stored objects with no message', sorted(only_objects))
        drift.log()
    return only_messages, only_objects


def reconcile_stored_objects(bucket=None, repair=False, batch_size=5000,
                             max_missing_repairs=RECONCILE_MAX_MISSING_REPAIRS):
    """Check the StoredObject index against blob storage and the message table.

    First each artifact storage, or just bucket if given, is diffed against its blobs
    by reconcile_bucket, which repairs the index when repair is set, except that live
    rows without bytes are repaired only up to max_missing_repairs per bucket, since
    they mean bytes were lost (see reconcile_bucket). Then every list
    whose messages live in one of those buckets is audited by audit_list_objects,
    which only reports. The order matters: the list audit reads the index, so it is
    trustworthy only once the index agrees with the bytes.

    Returns a dict of counts: the per-bucket counts summed across buckets (see
    reconcile_bucket), plus the lists audited, how many of them showed a mismatch,
    and the total hashcodes found on only one side.
    """
    buckets = list(settings.ARTIFACT_STORAGE_NAMES)
    if bucket is not None:
        if bucket not in buckets:
            raise ValueError(f'{bucket} is not an artifact storage')
        buckets = [bucket]

    stats = Counter()
    for name in buckets:
        stats.update(reconcile_bucket(
            name, repair=repair, batch_size=batch_size,
            max_missing_repairs=max_missing_repairs))

    stats.update(lists=0, list_mismatches=0, only_messages=0, only_objects=0)
    for elist in EmailList.objects.order_by('name'):
        if elist.blob_bucket not in buckets:
            continue
        only_messages, only_objects = audit_list_objects(elist)
        stats['lists'] += 1
        if only_messages or only_objects:
            stats['list_mismatches'] += 1
        stats['only_messages'] += len(only_messages)
        stats['only_objects'] += len(only_objects)

    logger.info(f'reconcile_stored_objects: {dict(stats)}')
    return dict(stats)
