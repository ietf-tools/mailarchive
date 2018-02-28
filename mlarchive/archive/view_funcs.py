"""
This module contains functions used in views.  We place them here to keep views "skinny"
and facilitate clean unit testing.
"""
import datetime
import math
import operator
import os
import random
import re
import string
import tarfile
import tempfile
from StringIO import StringIO

from django.conf import settings
from django.contrib import messages
from django.forms.formsets import formset_factory
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from haystack.views import SearchView

from mlarchive.archive.forms import RulesForm
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_lists_for_user
from mlarchive.utils.encoding import to_str

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
    for i in xrange(0, len(l), n):
        # yield l[i:i+n]
        result.append(l[i:i + n])
    return result


# --------------------------------------------------
# View Functions
# --------------------------------------------------

def custom_search_view_factory(view_class=SearchView, *args, **kwargs):
    """Modified version of haystack.views.search_view_factory() to support passed
    URL parameters
    See: https://github.com/django-haystack/django-haystack/issues/1063
    """
    def search_view(request, *vargs, **vkwargs):
        return view_class(*args, **kwargs)(request, *vargs, **vkwargs)
    return search_view


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
    lists = EmailList.objects.filter(name__in=get_lists_for_user(request)).order_by('name')

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


def get_export(sqs, export_type, request):
    """Process an export request"""

    # don't allow export of huge querysets and skip empty querysets
    count = sqs.count()
    redirect_url = '%s?%s' % (reverse('archive_search'), request.META['QUERY_STRING'])
    if (count > settings.EXPORT_LIMIT) or (count > settings.ANONYMOUS_EXPORT_LIMIT and not request.user.is_authenticated()):  # noqa
        messages.error(request, 'Too many messages to export.')
        return redirect(redirect_url)
    elif count == 0:
        messages.error(request, 'No messages to export.')
        return redirect(redirect_url)

    if export_type == 'url':
        return get_export_url(sqs, export_type, request)
    else:
        return get_export_tar(sqs, export_type, request)


def get_export_url(sqs, export_type, request):
    """Return file containing URLs of all messages in query results"""
    content = []
    for result in sqs:
        url = result.object.get_absolute_url()
        content.append(request.build_absolute_uri(url))
    return HttpResponse('\n'.join(content), content_type='text/plain')


def get_export_tar(sqs, export_type, request):
    """Returns a tar archive of messages

    sqs is SearchQuerySet object, the result of a search, and type is a string
    (mbox|maildir) the type of file to export.  It compiles messages from the queryset
    to the appropriate mail box type, in a zipped tarfile.  The function returns the
    tarfile, with seek(0) to reset for reading, and the filename as a string.
    """
    tardata = StringIO()
    tar = tarfile.open(fileobj=tardata, mode='w:gz')
    basename = get_random_basename(prefix=export_type)
    filename = basename + '.tar.gz'

    if export_type == 'maildir':
        tar = build_maildir_tar(sqs, tar, basename)
    elif export_type == 'mbox':
        tar = build_mbox_tar(sqs, tar, basename)

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


def build_maildir_tar(sqs, tar, basename):
    """Returns tar file with messages from SearchQuerySet in maildir format"""
    for result in sqs:
        arcname = os.path.join(basename, result.object.email_list.name, result.object.hashcode)
        tar.add(result.object.get_file_path(), arcname=arcname)
    return tar


def build_mbox_tar(sqs, tar, basename):
    """Returns tar file with messages from SearchQuerySet in mmox format.
    There are various problems adding non-file objects (ie. StringIO) to tar files
    therefore the mbox files are first built on disk
    """
    mbox_date = sqs[0].object.date.strftime('%Y-%m')
    mbox_list = sqs[0].object.email_list.name
    fd, temp_path = tempfile.mkstemp()
    mbox_file = os.fdopen(fd, 'w')
    for result in sqs:
        date = result.object.date.strftime('%Y-%m')
        mlist = result.object.email_list.name
        if date != mbox_date or mlist != mbox_list:
            mbox_file.close()
            tar.add(temp_path, arcname=os.path.join(basename,
                                                    mbox_list,
                                                    mbox_date + '.mbox'))
            os.remove(temp_path)
            fd, temp_path = tempfile.mkstemp()
            mbox_file = os.fdopen(fd, 'w')
            mbox_date = date
            mbox_list = mlist

        with open(result.object.get_file_path()) as input:
            # add envelope header
            from_line = to_str(result.object.get_from_line()) + '\n'
            mbox_file.write(from_line)
            mbox_file.write(input.read())
            mbox_file.write('\n')

    mbox_file.close()
    tar.add(temp_path, arcname=os.path.join(basename,
                                            mbox_list,
                                            mbox_date + '.mbox'))
    os.remove(temp_path)
    return tar


def get_message_index(query, message):
    """Returns the index of message in SearchQuerySetmessage, -1 if not found"""
    for n, result in enumerate(query):
        if result.object == message:
            return n
    return -1


def get_message_before(query, index):
    """Returns message of SearchQuerySet before index or None"""
    try:
        return query[index - 1].object
    except (IndexError, AssertionError):
        return None


def get_message_after(query, index):
    """Returns next message of SearchQuerySet after index or None"""
    try:
        return query[index + 1].object
    except IndexError:
        return None


def get_query_neighbors(query, message):
    """Returns a tuple previous_message and next_message given a message
    from the query results"""
    index = get_message_index(query, message)
    if index == -1:
        return None, None
    else:
        return get_message_before(query, index), get_message_after(query, index)


def get_query_string(request):
    """Returns the query string from the request, including '?' """
    return '?' + request.META['QUERY_STRING']
