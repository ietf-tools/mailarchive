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

#from mlarchive.archive.utils import get_html
from mlarchive.utils.decorators import check_access, superuser_only
from mlarchive.archive import actions

from models import *
from forms import *

import datetime
import mailbox
import math
import re
import os

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
        return extra
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

@superuser_only
def load(request):
    '''
    Load private list memebership
    '''
    # TODO do real implementation
    with open('/a/home/rcross/data/members') as f:
        members = f.readlines()

    return render_to_response('archive/load.html', {
        'members': members},
        RequestContext(request, {}),
    )

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
