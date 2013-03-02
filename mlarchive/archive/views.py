from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from haystack.views import SearchView, FacetedSearchView
#from mlarchive.archive.utils import get_html
from mlarchive.utils.decorators import check_access, superuser_only

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

    # def extra_context(self):

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
        os.chmod(settings.LOG_FILE,0666)
    
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
    test = u'Ond\u0159ej Sur\xfd<ondrej.sury@nic.cz>'
    msg = Message.objects.get(id=24190)
    body = msg.get_body()
    return render_to_response('archive/test.html', {
        'test': test,
        'body': body},
        RequestContext(request, {}),
    )
