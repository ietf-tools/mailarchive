from django.contrib import messages
from django.contrib.auth import logout
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from haystack.views import SearchView
from mlarchive.archive.utils import get_html
from mlarchive.http import Http403
from mlarchive.utils.decorators import check_access

from models import *
from forms import *

import datetime
import mailbox
import math
import re
import os

# --------------------------------------------------
# Classes
# --------------------------------------------------
class CustomSearchView(SearchView):
    '''
    A customized SearchView to add extra context
    '''
    def __name__(self):
        return "CustomSearchView"

    def build_form(self, form_kwargs=None):
        # add request to the form init call so we can use auth in processing
        return super(self.__class__,self).build_form(form_kwargs={ 'request' : self.request }) 
        
    def extra_context(self):
        extra = super(CustomSearchView, self).extra_context()

        extra['test'] = 'test'
        
        return extra
        
# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def chunks(l, n):
    '''
    Yield successive n-sized chunks from l.
    '''
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

# --------------------------------------------------
# STANDARD VIEW FUNCTIONS
# --------------------------------------------------
def advsearch(request):
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
    display_columns = 5
    form = BrowseForm()
    #assert False, request.user
    if request.user.is_authenticated():
        lists = EmailList.objects.filter(Q(active=True,private=False)|Q(members=request.user.pk)).order_by('name')
    else:
        lists = EmailList.objects.filter(active=True,private=False).order_by('name')
    columns = chunks(lists,int(math.ceil(lists.count()/float(display_columns))))
    
    return render_to_response('archive/browse.html', {
        'form': form,
        'lists': lists,
        'columns':columns},
        RequestContext(request, {}),
    )

def browse_list(request, list_name):
    # TODO change this
    name = list_name.split('@')[0]
    list_obj = get_object_or_404(EmailList, name=name)
    
    so = request.GET.get('so','date')
    
    if so in ('date','frm'):
        order = so
    msgs = Message.objects.filter(email_list=list_obj).order_by(order)
    
    return render_to_response('archive/browse_list.html', {
        'list_obj': list_obj,
        'msgs': msgs},
        RequestContext(request, {}),
    )

def browse_date(request, list_name):
    # TODO change this
    name = list_name.split('@')[0]
    list_obj = get_object_or_404(EmailList, name=name)
    
    msgs = Message.objects.filter(email_list=list_obj)
    
    return render_to_response('archive/browse.html', {
        'list_obj': list_obj,
        'msgs': msgs},
        RequestContext(request, {}),
    )
    
@check_access
def detail(request, list_name, id, msg):
    '''
    This view displays the requested message.
    NOTE: the "msg" arguments is added by check_access decorator
    '''
    msg_html = get_html(msg, None)
    
    return render_to_response('archive/detail.html', {
        'msg_html': msg_html},
        RequestContext(request, {}),
    )

# TODO: needs to be admin only
def load(request):
    '''
    Load private list memebership.
    '''
    with open('/a/home/rcross/data/members') as f:
        members = f.readlines()
    
    return render_to_response('archive/load.html', {
        'members': members},
        RequestContext(request, {}),
    )

def logout_view(request):
    logout(request)
    return HttpResponseRedirect('/archive/')
    
def main(request):
    '''
    The main page.  This page contains a simple search form and some links.
    '''
    form = SearchForm()
    
    #assert False, request
    return render_to_response('archive/main.html', {
        'form': form},
        RequestContext(request, {}),
    )

# --------------------------------------------------
# TEST FUNCTIONS
# --------------------------------------------------


