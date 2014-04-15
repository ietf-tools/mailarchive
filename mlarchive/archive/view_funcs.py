"""
This module contains functions used in views.  We place them here to keep views "skinny"
and facilitate clean unit testing.
"""
import datetime
import math
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

def get_export(sqs, type, request):
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

    #tardata, filename = get_export(queryset, type)

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
                if result.object.from_line:
                    mbox_file.write(result.object.from_line + '\n')
                else:
                    mbox_file.write('From {0} {1}\n'.format(
                        result.object.frm_email,
                        result.object.date.strftime('%a %b %d %H:%M:%S %Y')))
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
