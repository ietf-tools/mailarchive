"""
This module contains functions used in views.  We place them here to keep views "skinny"
and facilitate clean unit testing.
"""
from builtins import range

import datetime
import math
import os
import random
import re
import string
import tarfile
import tempfile
from io import BytesIO
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.forms.formsets import formset_factory
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.encoding import smart_bytes

from mlarchive.archive.forms import RulesForm
from mlarchive.archive.models import EmailList, Message
from mlarchive.archive.utils import get_lists_for_user


contain_pattern = re.compile(r'(?P<neg>[-]?)(?P<field>[a-z]+):\((?P<value>[^\)]+)\)')
exact_pattern = re.compile(r'(?P<neg>[-]?)(?P<field>[a-z]+):\"(?P<value>[^\"]+)\"')


# --------------------------------------------------
# Classes
# --------------------------------------------------

'''
class SearchResult(object):
    def __init__(self, object):
        self.object = object

    @property
    def subject(self):
        return self.object.subject

    @property
    def frm_name(self):
        return self.object.frm_name

    @property
    def date(self):
        return self.object.date
'''

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def chunks(l, n):
    """Yield successive n-sized chunks from l"""
    result = []
    for i in range(0, len(l), n):
        # yield l[i:i+n]
        result.append(l[i:i + n])
    return result


def apply_objects(hits):
    '''Add object attribute (Message) to list of hits,
    to simulate Haystack results'''
    for hit in hits:
        hit.object = Message.objects.get(pk=hit.django_id)

# --------------------------------------------------
# View Functions
# --------------------------------------------------


def initialize_formsets(query):
    """Initialize advanced search form formsets based on the query.
    Used when the GET of advanced search includes URL parameters, in other words
    we are returning to modify the search
    """
    RulesFormset0 = formset_factory(RulesForm, extra=0)
    RulesFormset1 = formset_factory(RulesForm, extra=1)

    qinitial = []
    ninitial = []

    while query:
        query = query.lstrip()
        if re.search(contain_pattern, query):
            match = re.search(contain_pattern, query)
            d = {'field': match.groupdict()['field'],
                 'value': match.groupdict()['value'],
                 'qualifier': 'contains'}
            if match.groupdict()['neg']:
                ninitial.append(d)
            else:
                qinitial.append(d)
            query, n = re.subn(contain_pattern, '', query, 1)
        elif re.search(exact_pattern, query):
            match = re.search(exact_pattern, query)
            d = {'field': match.groupdict()['field'],
                 'value': match.groupdict()['value'],
                 'qualifier': 'exact'}
            if match.groupdict()['neg']:
                ninitial.append(d)
            else:
                qinitial.append(d)
            query, n = re.subn(exact_pattern, '', query, 1)
        else:
            query = query[1:]

    if qinitial:
        query_formset = RulesFormset0(prefix='query', initial=qinitial)
    else:
        query_formset = RulesFormset1(prefix='query')
    if ninitial:
        not_formset = RulesFormset0(prefix='not', initial=ninitial)
    else:
        not_formset = RulesFormset1(prefix='not')

    return query_formset, not_formset


def get_columns(request):
    """Returns email lists the user can view, grouped in columns for display.
    columns is a dictionary of lists containing keys: active, inactive, private
    """
    display_columns = 5
    columns = {'private': [], 'active': [], 'inactive': []}
    lists = EmailList.objects.filter(name__in=get_lists_for_user(request.user)).order_by('name')

    private = lists.filter(private=True)
    if private:
        columns['private'] = chunks(private, int(math.ceil(private.count() / float(display_columns))))

    active = lists.filter(active=True, private=False)
    if active:
        columns['active'] = chunks(active, int(math.ceil(active.count() / float(display_columns))))

    inactive = lists.filter(active=False, private=False)
    if inactive:
        columns['inactive'] = chunks(inactive, int(math.ceil(inactive.count() / float(display_columns))))

    return columns


def get_export(search, export_type, request):
    """Process an export request"""

    # don't allow export of huge querysets and skip empty querysets
    count = search.count()
    redirect_url = '%s?%s' % (reverse('archive_search'), request.META['QUERY_STRING'])
    if count == 0:
        messages.error(request, 'No messages to export.')
        return redirect(redirect_url)
    elif request.user.is_superuser:
        pass
    elif not request.user.is_authenticated and count > settings.ANONYMOUS_EXPORT_LIMIT:
        messages.error(request, f'Export exceeds message limit of {settings.ANONYMOUS_EXPORT_LIMIT}')
        return redirect(redirect_url)
    elif count > settings.EXPORT_LIMIT:  # noqa
        messages.error(request, f'Export exceeds message limit of {settings.EXPORT_LIMIT}')
        return redirect(redirect_url)
    search = search.params(preserve_order=True)
    results = list(search.scan())
    apply_objects(results)
    if export_type == 'url':
        return get_export_url(results, export_type, request)
    else:
        return get_export_tar(results, export_type, request)


def get_export_url(results, export_type, request):
    """Return file containing URLs of all messages in query results"""
    content = []
    for result in results:
        url = result.object.get_absolute_url()
        content.append(request.build_absolute_uri(url))
    return HttpResponse('\n'.join(content), content_type='text/plain')


def get_export_tar(results, export_type, request):
    """Returns a tar archive of messages

    sqs is SearchQuerySet object, the result of a search, and type is a string
    (mbox|maildir) the type of file to export.  It compiles messages from the queryset
    to the appropriate mail box type, in a zipped tarfile.  The function returns the
    tarfile, with seek(0) to reset for reading, and the filename as a string.
    """
    tardata = BytesIO()
    tar = tarfile.open(fileobj=tardata, mode='w:gz')
    basename = get_random_basename(prefix=export_type)
    filename = basename + '.tar.gz'

    if export_type == 'maildir':
        tar = build_maildir_tar(results, tar, basename)
    elif export_type == 'mbox':
        tar = build_mbox_tar(results, tar, basename)

    tar.close()
    tardata.seek(0)

    response = HttpResponse(tardata.read())
    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    response['Content-Type'] = 'application/x-tar-gz'
    tardata.close()
    return response


def get_random_basename(prefix):
    """Returns a string [prefix][date]_[random characters]"""
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + '_'
    rand = ''.join(random.choice(chars) for x in range(5))
    now = datetime.datetime.now()
    return '{prefix}{date}_{random}'.format(
        prefix=prefix,
        date=now.strftime('%m%d'),
        random=rand
    )


def get_random_token(length=32):
    return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(length)])


def build_maildir_tar(results, tar, basename):
    """Returns tar file with messages from SearchQuerySet in maildir format"""
    for result in results:
        arcname = os.path.join(basename, result.object.email_list.name, result.object.hashcode)
        tar.add(result.object.get_file_path(), arcname=arcname)
    return tar


def build_mbox_tar(results, tar, basename):
    """Returns tar file with messages from SearchQuerySet in mmox format.
    There are various problems adding non-file objects (ie. StringIO) to tar files
    therefore the mbox files are first built on disk
    """
    mbox_date = results[0].object.date.strftime('%Y-%m')
    mbox_list = results[0].object.email_list.name
    fd, temp_path = tempfile.mkstemp()
    mbox_file = os.fdopen(fd, 'wb')
    for result in results:
        date = result.object.date.strftime('%Y-%m')
        mlist = result.object.email_list.name
        if date != mbox_date or mlist != mbox_list:
            mbox_file.close()
            tar.add(temp_path, arcname=os.path.join(basename,
                                                    mbox_list,
                                                    mbox_date + '.mbox'))
            os.remove(temp_path)
            fd, temp_path = tempfile.mkstemp()
            mbox_file = os.fdopen(fd, 'wb')
            mbox_date = date
            mbox_list = mlist

        with open(result.object.get_file_path(), 'rb') as input:
            # add envelope header if missing
            if not input.read(5) == b'From ':
                from_line = smart_bytes(result.object.get_from_line()) + b'\n'
                mbox_file.write(from_line)
            input.seek(0)
            mbox_file.write(input.read())
            mbox_file.write(b'\n')

    mbox_file.close()
    tar.add(temp_path, arcname=os.path.join(basename,
                                            mbox_list,
                                            mbox_date + '.mbox'))
    os.remove(temp_path)
    return tar


def get_message_index(response, message):
    """Returns the index of message in search response, -1 if not found"""
    for n, result in enumerate(response):
        if result.object == message:
            return n
    return -1


def get_message_before(response, index):
    """Returns message of search response before index or None"""
    if index == 0:
        return None
    else:
        return response[index - 1].object


def get_message_after(response, index):
    """Returns next message of search response after index or None"""
    try:
        return response[index + 1].object
    except IndexError:
        return None


def get_query_neighbors(search, message):
    """Returns a tuple previous_message and next_message given a message
    from the query results"""
    response = search.execute()
    apply_objects(response)
    index = get_message_index(response, message)
    if index == -1:
        return None, None
    else:
        return get_message_before(response, index), get_message_after(response, index)


def get_query_string(request):
    """Returns the query string from the request, including '?' """
    return '?' + request.META['QUERY_STRING']
