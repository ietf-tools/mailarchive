from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from haystack.views import SearchView, FacetedSearchView
from haystack.query import SearchQuerySet
from StringIO import StringIO
from mlarchive.utils.decorators import check_access, superuser_only
from mlarchive.archive import actions

from models import *
from forms import *

import datetime
import math
import re
import os
import random
import string
import tarfile
import tempfile


from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Classes
# --------------------------------------------------
class CustomSearchView(FacetedSearchView):
    '''
    A customized SearchView.  Need to add request object to the form init so we can use it
    for authorization
    '''
    def __name__(self):
        return "CustomSearchView"

    def build_form(self, form_kwargs=None):
        return super(self.__class__,self).build_form(form_kwargs={ 'request' : self.request })

    def extra_context(self):
        extra = super(CustomSearchView, self).extra_context()
        match = re.search(r"^email_list=([a-zA-Z0-9\_\-]+)",self.request.META['QUERY_STRING'])
        if match:
            try:
                browse_list = EmailList.objects.get(name=match.group(1))
            except EmailList.DoesNotExist:
                browse_list = None
        else:
            browse_list = None
        extra['browse_list'] = browse_list
        extra['export_mbox'] = self.request.META['REQUEST_URI'].replace('/archive/search/','/archive/export/mbox/')
        extra['export_maildir'] = self.request.META['REQUEST_URI'].replace('/archive/search/','/archive/export/maildir/')
        if 'as' not in self.request.GET:
            extra['modify_search_url'] = self.request.META['REQUEST_URI'].replace('/archive/search/','/archive/')
        else:
            extra['modify_search_url'] = self.request.META['REQUEST_URI'].replace('/archive/search/','/archive/advsearch/')
        return extra

    # override this for export
    #def create_response(self):
# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def chunks(l, n):
    '''
    Yield successive n-sized chunks from l
    '''
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

# --------------------------------------------------
# STANDARD VIEW FUNCTIONS
# --------------------------------------------------
#@user_passes_test(lambda u: u.is_superuser)
@superuser_only
def admin(request):
    '''
    Administrator View.  Only accessible by the superuser this view allows
    the administrator to delete spam messages
    '''
    results = None
    if request.method == 'POST':
        if 'action' not in request.POST:
            form = AdminForm(request.POST)
            if form.is_valid():
                kwargs = {}
                email_list = form.cleaned_data['email_list']
                end_date = form.cleaned_data['end_date']
                frm = form.cleaned_data['frm']
                msgid = form.cleaned_data['msgid']
                subject = form.cleaned_data['subject']
                spam = form.cleaned_data['spam']
                start_date = form.cleaned_data['start_date']
                if email_list:
                    kwargs['email_list'] = email_list.name
                if end_date:
                    kwargs['date__lte'] = end_date
                if frm:
                    kwargs['frm'] = frm
                if msgid:
                    kwargs['msgid'] = msgid
                if subject:
                    kwargs['subject'] = subject
                if spam:
                    kwargs['spam_score__gt'] = 0
                if start_date:
                    kwargs['date__gte'] = start_date

                if kwargs:
                    results = SearchQuerySet().filter(**kwargs)
        else:
            action = request.POST.get('action')
            func = getattr(actions, action)
            selected = request.POST.getlist('_selected_action')
            queryset = Message.objects.filter(pk__in=selected)
            return func(request, queryset)

    else:
        form = AdminForm()

    return render_to_response('archive/admin.html', {
        'results': results,
        'form': form},
        RequestContext(request, {}),
    )

def advsearch(request):
    '''
    The Advanced Search View
    '''
    if request.GET:
        # reverse engineer advanced search form from query string
        form = AdvancedSearchForm(request=request,initial=request.GET)
        qinitial = []
        ninitial = []
        params = request.GET.get('q').split()
        for param in params:
            d = {}
            key,val = param.split(':')
            d['field'] = key.lstrip('-')
            d['value'] = val.strip('"')
            if '"' in val:
                d['qualifier'] = 'exact'
            else:
                d['qualifier'] = 'contains'
            if key.startswith('-'):
                ninitial.append(d)
            else:
                qinitial.append(d)
        RulesFormset0 = formset_factory(RulesForm,extra=0)
        RulesFormset1 = formset_factory(RulesForm,extra=1)
        if qinitial:
            query_formset = RulesFormset0(prefix='query',initial=qinitial)
        else:
            query_formset = RulesFormset1(prefix='query',initial=qinitial)
        if ninitial:
            not_formset = RulesFormset0(prefix='not',initial=ninitial)
        else:
            not_formset = RulesFormset1(prefix='not',initial=ninitial)
    else:
        form = AdvancedSearchForm(request=request)
        RulesFormset = formset_factory(RulesForm)
        query_formset = RulesFormset(prefix='query')
        not_formset = RulesFormset(prefix='not')

    return render_to_response('archive/advsearch.html', {
        'form': form,
        'query_formset': query_formset,
        'not_formset': not_formset},
        RequestContext(request, {}),
    )

def browse(request):
    '''
    This view presents a list of Email Lists the user has access to
    '''
    display_columns = 5
    form = BrowseForm()
    if request.user.is_authenticated():
        if request.user.is_superuser:
            lists = EmailList.objects.filter(private=True).order_by('name')
        else:
            lists = EmailList.objects.filter(private=True,members=request.user.pk).order_by('name')
        private_columns = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))
    else:
        private_columns = []

    lists = EmailList.objects.filter(active=True,private=False).order_by('name')
    active_columns = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))

    lists = EmailList.objects.filter(active=False,private=False).order_by('name')
    if lists:
        inactive_columns = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))
    else:
        inactive_columns = []

    return render_to_response('archive/browse.html', {
        'form': form,
        'private_columns': private_columns,
        'active_columns': active_columns,
        'inactive_columns': inactive_columns},
        RequestContext(request, {}),
    )

# TODO if we use this, need access decorator
def browse_list(request, list_name):
    '''
    Browse emails by list
    '''
    list_obj = get_object_or_404(EmailList, name=list_name)

    # default sort order is date descending
    order = request.GET.get('so','-date')
    if not order in ('date','-date','frm','-frm'):
        order = '-date'
    msgs = Message.objects.filter(email_list=list_obj).order_by(order)

    return render_to_response('archive/browse_list.html', {
        'list_obj': list_obj,
        'msgs': msgs},
        RequestContext(request, {}),
    )

@check_access
def detail(request, list_name, id, msg):
    '''
    This view displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    '''
    msg_html = msg.get_body_html()

    return render_to_response('archive/detail.html', {
        'msg_html': msg_html},
        RequestContext(request, {}),
    )

def export(request, type):
    '''
    This view takes a search query string and builds a gzipped tar archive of the messages
    in the query results  Two formats are supported: maildir and mbox.
    '''
    # force sort order and run query
    data = request.GET.copy()
    data['so'] = 'email_list'
    data['sso'] = 'date'
    form = AdvancedSearchForm(data,load_all=False,request=request)
    results = form.search()

    # don't allow export of huge querysets and skip empty querysets
    count = results.count()
    if count > 50000:
        # message user
        # return to original query
        raise Exception
    elif count == 0:
        # message user
        # return to original query
        pass

    tardata = StringIO()
    tar = tarfile.open(fileobj=tardata, mode='w:gz')

    if type == 'maildir':
        for result in results:
            arcname = os.path.join(result.object.email_list.name,result.object.hashcode)
            tar.add(result.object.get_file_path(),arcname=arcname)
    elif type == 'mbox':
        # there are various problems adding non-file objects (ie. StringIO) to tar files
        # therefore the mbox files are first built on disk
        mbox_date = results[0].object.date.strftime('%Y-%m')
        mbox_list = results[0].object.email_list.name
        fd, temp_path = tempfile.mkstemp()
        mbox_file = os.fdopen(fd,'w')
        for result in results:
            date = result.object.date.strftime('%Y-%m')
            mlist = result.object.email_list.name
            if date != mbox_date or mlist != mbox_list:
                mbox_file.close()
                tar.add(temp_path,arcname=mbox_list + '/' + mbox_date + '.mail')
                os.remove(temp_path)
                fd, temp_path = tempfile.mkstemp()
                mbox_file = os.fdopen(fd,'w')
                mbox_date = date
                mbox_list = mlist

            with open(result.object.get_file_path()) as input:
                # TODO: if no envelope add one
                mbox_file.write(input.read())
                mbox_file.write('\n')

        mbox_file.close()
        tar.add(temp_path,arcname=mbox_list + '/' + mbox_date + '.mail')
        os.remove(temp_path)

    tar.close()
    tardata.seek(0)

    # make filename
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + '_'
    rand = ''.join(random.choice(chars) for x in range(5))
    now = datetime.datetime.now()
    filename = 'exp%s_%s.tgz' % (now.strftime('%m%d'),rand)

    response = HttpResponse(tardata.read())
    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    response['Content-Type'] = 'application/x-gzip'
    tardata.close()
    return response

def logout_view(request):
    '''
    Logout the user
    '''
    logout(request)
    return HttpResponseRedirect('/archive/')

def main(request):
    '''
    The main page.  This page contains a simple search form and some links.
    '''
    if request.GET:
        form = SearchForm(request.GET)
    else:
        form = SearchForm()

    if os.path.exists(settings.LOG_FILE):
        try:
            os.chmod(settings.LOG_FILE,0666)
        except OSError:
            pass

    return render_to_response('archive/main.html', {
        'form': form},
        RequestContext(request, {}),
    )

# --------------------------------------------------
# TEST FUNCTIONS
# --------------------------------------------------
def test(request):
    #from django.core.exceptions import PermissionDenied
    #raise PermissionDenied
    tests = [u'Ond\u0159ej Sur\xfd<ondrej.sury@nic.cz>',
            u'P \xe4r Mattsson <per@defero.se>']
    msg = Message.objects.get(id=1)
    body = msg.get_body()
    return render_to_response('archive/test.html', {
        'tests': tests,
        'body': body},
        RequestContext(request, {}),
    )
