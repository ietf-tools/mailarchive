from django.contrib import messages
from django.core.urlresolvers import reverse
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from haystack.views import SearchView

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
    form = AdvancedSearchForm()
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

def detail(request, list_name, id):
    message = get_object_or_404(Message, hashcode=id)

    return render_to_response('archive/detail.html', {
        'message': message},
        RequestContext(request, {}),
    )
    
def main(request):
    '''
    The main page.  This page contains a simple search form and some links.
    '''
    form = SearchForm()
    
    return render_to_response('archive/main.html', {
        'form': form},
        RequestContext(request, {}),
    )

# --------------------------------------------------
# TEST FUNCTIONS
# --------------------------------------------------


