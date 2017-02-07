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
from django.core.urlresolvers import reverse
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import redirect

from mlarchive.archive.forms import RulesForm
from mlarchive.archive.models import EmailList
from mlarchive.utils.encoding import to_str

contain_pattern = re.compile(r'(?P<neg>[-]?)(?P<field>[a-z]+):\((?P<value>[^\)]+)\)')
exact_pattern = re.compile(r'(?P<neg>[-]?)(?P<field>[a-z]+):\"(?P<value>[^\"]+)\"')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def chunks(l, n):
    """Yield successive n-sized chunks from l"""
    result = []
    for i in xrange(0, len(l), n):
        #yield l[i:i+n]
        result.append(l[i:i+n])
    return result

# --------------------------------------------------
# View Functions
# --------------------------------------------------
def find_message_date(sqs, msg, reverse=False):
    """Returns the position message occurs in the SearchQuerySet.  Use
    binary search to locate the record.  Expects query set sorted by
    date ascending unless reverse=True.
    """
    lo = 0
    hi = sqs.count() - 1
    if hi == -1:            # abort if queryset is empty
        return -1

    if reverse:
        compare = operator.gt
    else:
        compare = operator.lt

    while lo <= hi:
        mid = (lo+hi)/2
        midval = sqs[mid]
        if compare(midval.date,msg.date):
            lo = mid+1
        elif midval.date == msg.date:
            break
        else:
            hi = mid

    if midval.object == msg:
        return mid
    if midval.date != msg.date:
        return -1

    # we get here if there are messages with the exact same date
    # find the first message with this date
    count = sqs.count()
    pre = mid - 1
    while pre >= 0 and sqs[pre].date == msg.date:
        mid = pre
        pre = pre - 1
    # search forward
    while mid < count and sqs[mid].date == msg.date:
        if sqs[mid].object == msg:
            return mid
        mid = mid + 1

    return -1


def find_message_gbt(sqs,msg, reverse=False):
    """Returns the position of message (msg) in queryset (sqs)
    for queries grouped by thread.  Uses binary search to locate the thread,
    then traverses the thread.
    reverse=True: threads ordered descending
    reverse=False: threads ordered ascending
    """
    last_index = sqs.count() - 1
    
    lo = 0
    hi = last_index
    if hi == -1:            # abort if queryset is empty
        return -1
    if hi == 0:             # simple check if queryset is length of 1
        if sqs[0].object == msg:
            return 0
        else:
            return -1

    cdate = msg.thread.date
    # first locate the thread
    if reverse:
        compare = operator.gt
    else:
        compare = operator.lt
    while lo < hi:
        mid = (lo+hi)/2
        midval = sqs[mid]
        if compare(midval.object.thread.date,cdate):
            lo = mid+1
        elif midval.object.thread.date == cdate:
            break
        else:
            hi = mid

    if midval.object == msg:
        return mid

    # traverse thread
    # determine most likely direction to search, assumes ascending order
    thread_date = midval.object.thread.date
    if midval.object.date <= msg.date:
        step = 1
    elif midval.object.date > msg.date:
        step = -1

    # try searching in the most likely direction
    starting_point = mid
    while 0 <= mid <= last_index and sqs[mid].object.thread.date == thread_date:
        if sqs[mid].object == msg:
            return mid
        mid = mid + step

    # didn't find. try the other direction
    mid = starting_point
    while 0 <= mid <= last_index and sqs[mid].object.thread.date == thread_date:
        if sqs[mid].object == msg:
            return mid
        mid = mid - step

    # didn't find message
    return -1


def initialize_formsets(query):
    """Initialize advanced search form formsets based on the query.
    Used when the GET of advanced search includes URL parameters, in other words
    we are returning to modify the search
    """
    RulesFormset0 = formset_factory(RulesForm,extra=0)
    RulesFormset1 = formset_factory(RulesForm,extra=1)

    qinitial = []
    ninitial = []

    while query:
        query = query.lstrip()
        if re.search(contain_pattern,query):
            mat = re.search(contain_pattern,query)
            d = {'field':mat.groupdict()['field'],
                 'value':mat.groupdict()['value'],
                 'qualifier':'contains'}
            if mat.groupdict()['neg']:
                ninitial.append(d)
            else:
                qinitial.append(d)
            query, n = re.subn(contain_pattern,'',query,1)
        elif re.search(exact_pattern,query):
            mat = re.search(exact_pattern,query)
            d = {'field':mat.groupdict()['field'],
                 'value':mat.groupdict()['value'],
                 'qualifier':'exact'}
            if mat.groupdict()['neg']:
                ninitial.append(d)
            else:
                qinitial.append(d)
            query, n = re.subn(exact_pattern,'',query,1)
        else:
            query = query[1:]

    if qinitial:
        query_formset = RulesFormset0(prefix='query',initial=qinitial)
    else:
        query_formset = RulesFormset1(prefix='query')
    if ninitial:
        not_formset = RulesFormset0(prefix='not',initial=ninitial)
    else:
        not_formset = RulesFormset1(prefix='not')

    return query_formset, not_formset

def is_javascript_disabled(request):
    if 'nojs' in request.GET:
        return True
    else:
        return False


def get_browse_list(request):
    """Return the list name if this query is a browse list query"""
    query_string = get_query_string(request)
    match = re.search(r"^\?email_list=([a-zA-Z0-9\_\-]+)",query_string)
    if match:
        try:
            browse_list = EmailList.objects.get(name=match.group(1))
        except EmailList.DoesNotExist:
            browse_list = None
    else:
        browse_list = None
    return browse_list


def get_columns(user):
    """Returns email lists the user can view, grouped in columns for display.
    columns is a dictionary of lists containing keys: active, inactive, private
    """
    display_columns = 5
    columns = {'private':[],'active':[],'inactive':[]}

    # private columns
    if user.is_authenticated():
        if user.is_superuser:
            lists = EmailList.objects.filter(private=True).order_by('name')
        else:
            lists = EmailList.objects.filter(private=True,members=user.pk).order_by('name')
        if lists:
            columns['private'] = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))

    # active columns
    lists = EmailList.objects.filter(active=True,private=False).order_by('name')
    if lists:
        columns['active'] = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))

    # inactive columns
    lists = EmailList.objects.filter(active=False,private=False).order_by('name')
    if lists:
        columns['inactive'] = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))

    return columns

def get_export(sqs, export_type, request):
    """Process an export request"""
    if export_type == 'url':
        return get_export_url(sqs,export_type,request)
    else:
        return get_export_tar(sqs,export_type,request)

def get_export_url(sqs, export_type, request):
    """Return file containing URLs of all messages in query results"""
    content = []
    for result in sqs:
        url = result.object.get_absolute_url()
        content.append(request.build_absolute_uri(url))
    return HttpResponse('\n'.join(content), content_type='text/plain')

def get_export_tar(sqs, type, request):
    """Returns a tar archive of messages

    sqs is SearchQuerySet object, the result of a search, and type is a string
    (mbox|maildir) the type of file to export.  It compiles messages from the queryset
    to the appropriate mail box type, in a zipped tarfile.  The function returns the
    tarfile, with seek(0) to reset for reading, and the filename as a string.
    """
    # don't allow export of huge querysets and skip empty querysets
    count = sqs.count()
    redirect_url = '%s?%s' % (reverse('archive_search'), request.META['QUERY_STRING'])
    if count > settings.EXPORT_LIMIT:
        messages.error(request,'Too many messages to export.')
        return redirect(redirect_url)
    elif count == 0:
        messages.error(request,'No messages to export.')
        return redirect(redirect_url)

    tardata = StringIO()
    tar = tarfile.open(fileobj=tardata, mode='w:gz')

    # make filename
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + '_'
    rand = ''.join(random.choice(chars) for x in range(5))
    now = datetime.datetime.now()
    basename = '%s%s_%s' % (type,now.strftime('%m%d'),rand)
    filename = basename + '.tar.gz'

    if type == 'maildir':
        for result in sqs:
            arcname = os.path.join(basename,result.object.email_list.name,result.object.hashcode)
            tar.add(result.object.get_file_path(),arcname=arcname)
    elif type == 'mbox':
        # there are various problems adding non-file objects (ie. StringIO) to tar files
        # therefore the mbox files are first built on disk
        mbox_date = sqs[0].object.date.strftime('%Y-%m')
        mbox_list = sqs[0].object.email_list.name
        fd, temp_path = tempfile.mkstemp()
        mbox_file = os.fdopen(fd,'w')
        for result in sqs:
            date = result.object.date.strftime('%Y-%m')
            mlist = result.object.email_list.name
            if date != mbox_date or mlist != mbox_list:
                mbox_file.close()
                tar.add(temp_path,arcname=os.path.join(basename,
                                                       mbox_list,
                                                       mbox_date + '.mbox'))
                os.remove(temp_path)
                fd, temp_path = tempfile.mkstemp()
                mbox_file = os.fdopen(fd,'w')
                mbox_date = date
                mbox_list = mlist

            with open(result.object.get_file_path()) as input:
                # add envelope header
                from_line = to_str(result.object.get_from_line()) + '\n'
                mbox_file.write(from_line)
                mbox_file.write(input.read())
                mbox_file.write('\n')

        mbox_file.close()
        tar.add(temp_path,arcname=os.path.join(basename,
                                               mbox_list,
                                               mbox_date + '.mbox'))
        os.remove(temp_path)

    tar.close()
    tardata.seek(0)

    response = HttpResponse(tardata.read())
    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    response['Content-Type'] = 'application/x-tar-gz'
    tardata.close()
    return response


def get_message_index(query,message):
    """Returns the index of message in SearchQuerySetmessage, -1 if not found"""
    for n,result in enumerate(query):
        if result.object == message:
            return n
    return -1

def get_message_before(query,index):
    """Returns message of SearchQuerySet before index or None"""
    try:
        return query[index-1].object
    except (IndexError, AssertionError):
        return None

def get_message_after(query,index):
    """Returns next message of SearchQuerySet after index or None"""
    try:
        return query[index+1].object
    except IndexError:
        return None

def get_query_neighbors(query,message):
    """Returns a tuple previous_message and next_message given a message
    from the query results"""
    index = get_message_index(query,message)
    if index == -1:
        return None,None
    else:
        return get_message_before(query,index),get_message_after(query,index)

def get_query_string(request):
    """Returns the query string from the request, including '?' """
    return '?' + request.META['QUERY_STRING']
