import json
import re
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from haystack.views import SearchView, FacetedSearchView
from haystack.query import SearchQuerySet

from mlarchive.utils.decorators import check_access, superuser_only, pad_id
from mlarchive.archive import actions
from mlarchive.archive.query_utils import get_kwargs
from mlarchive.archive.view_funcs import (initialize_formsets, get_columns, get_export, 
    find_message_date, find_message_date_reverse, find_message_gbt)

from models import *
from forms import *

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Classes
# --------------------------------------------------
class CustomSearchView(SearchView):
    """A customized SearchView.  Need to add request object to the form init so we can
    use it for authorization
    """
    def __name__(self):
        return "CustomSearchView"

    def __call__(self, request):
        """Generates the actual response to the search.

        Relies on internal, overridable methods to construct the response.

        CUSTOM: as soon as queryset is returned from get_results() check for custom
        attribute myfacets and save to SearchView so we can add to context in
        extra_context().  This is required because create_response() corrupts regular
        facet_counts().
        """
        self.request = request

        self.form = self.build_form()
        self.query = self.get_query()
        self.results = self.get_results()
        if hasattr(self.results,'myfacets'):
            self.myfacets = self.results.myfacets
        if hasattr(self.results,'queryid'):
            self.queryid = self.results.queryid

        return self.create_response()


    def build_form(self, form_kwargs=None):
        return super(self.__class__,self).build_form(form_kwargs={ 'request' : self.request })

    def build_page(self):
        """Returns tuple of: 
        - subset of results for display
        - queryset offset: the offset of results subset within entire queryset
        - selected offset: the offset of message specified in query arguments within
        results subset
        
        If request arguments include "index", returns slice of results containing
        message named in "index" with appropriate offset within slice, otherwise returns
        first #(results_per_page) messages and offsets=0.
        """
        buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
        index = self.request.GET.get('index')
        if index:
            position = self.find_message(index)
            if position == -1:
                raise Http404("No such message!")
            start = position - buffer if position > buffer else 0
            selected_offset = position if position < buffer else buffer
            return (self.results[start:position + self.results_per_page + 1], start, selected_offset)
        else:
            return (self.results[:self.results_per_page + 1],0,0)

    def extra_context(self):
        """Add variables to template context"""
        extra = super(CustomSearchView, self).extra_context()
        query_string = '?' + self.request.META['QUERY_STRING']

        # browse list
        match = re.search(r"^email_list=([a-zA-Z0-9\_\-]+)",query_string)
        if match:
            try:
                browse_list = EmailList.objects.get(name=match.group(1))
            except EmailList.DoesNotExist:
                browse_list = None
        else:
            browse_list = None
        extra['browse_list'] = browse_list

        # thread sort
        if 'gbt' in self.request.GET:
            extra['thread_sorted'] = True
        else:
            extra['thread_sorted'] = False

        # export links
        extra['export_mbox'] = reverse('archive_export',kwargs={'type':'mbox'}) + query_string
        extra['export_maildir'] = reverse('archive_export',kwargs={'type':'maildir'})+ query_string

        # modify search link
        if 'as' not in self.request.GET:
            extra['modify_search_url'] = reverse('archive') + query_string
        else:
            extra['modify_search_url'] = reverse('archive_advsearch') + query_string

        # add custom facets
        if hasattr(self,'myfacets'):
            extra['facets'] = self.myfacets

        if hasattr(self,'queryid'):
            extra['queryid'] = self.queryid

        return extra

    def find_message(self,hash):
        """Returns the position of message identified by hash in self.results.
        Currently only supports 'grouped by thread' and date sort order.
        """
        try:
            msg = Message.objects.get(hashcode=hash+'=')
        except Message.DoesNotExist:
            raise Http404("No such message!")
        
        if self.request.GET.get('gbt'):
            return find_message_gbt(self.results,msg)
        elif self.request.GET.get('so') == 'date':
            return find_message_date(self.results,msg)
        else:
            return find_message_date_reverse(self.results,msg)

    def create_response(self):
        """
        Generates the actual HttpResponse to send back to the user.
        """
        results, queryset_offset, selected_offset = self.build_page()

        context = {
            'query': self.query,
            'form': self.form,
            'results': results,
            'count': self.results.count(),
            'suggestion': None,
            'queryset_offset': queryset_offset,
            'selected_offset': selected_offset,
        }

        if self.results and hasattr(self.results, 'query') and self.results.query.backend.include_spelling:
            context['suggestion'] = self.form.get_suggestion()

        context.update(self.extra_context())
        return render_to_response(self.template, context, context_instance=self.context_class(self.request))

# --------------------------------------------------
# STANDARD VIEW FUNCTIONS
# --------------------------------------------------
#@user_passes_test(lambda u: u.is_superuser)
@superuser_only
def admin(request):
    """Administrator View.  Only accessible by the superuser this view allows
    the administrator to run queries and perform actions, ie. remove spam, on the 
    results.  Available actions are defined in actions.py
    """
    results = None
    if request.method == 'POST':
        if 'action' not in request.POST:
            form = AdminForm(request.POST)
            if form.is_valid():
                kwargs = get_kwargs(form.cleaned_data)
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

@superuser_only
def admin_console(request):
    form = None
    return render_to_response('archive/admin_console.html', {
        'form': form},
        RequestContext(request, {}),
    )

@superuser_only
def admin_guide(request):
    return render_to_response('archive/admin_guide.html', {},
        RequestContext(request, {}),
    )

def advsearch(request):
    """Advanced Search View"""
    if request.GET:
        # reverse engineer advanced search form from query string
        form = AdvancedSearchForm(request=request,initial=request.GET)
        query_formset, not_formset = initialize_formsets(request.GET.get('q'))
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

def browse(request, list_name=None):
    """Presents a list of Email Lists the user has access to.  There are
    separate sections for private, active and inactive.
    """
    if list_name:
        redirect_url = '%s?%s' % (reverse('archive_search'), 'email_list=' + list_name)
        return redirect(redirect_url)
        
    form = BrowseForm()
    columns = get_columns(request.user)

    return render_to_response('archive/browse.html', {
        'form': form,
        'columns': columns},
        RequestContext(request, {}),
    )

# TODO if we use this, need access decorator
def browse_list(request, list_name):
    """Browse emails by list.  The simple version."""
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

@pad_id
@check_access
def detail(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    return render_to_response('archive/detail.html', {
        'msg':msg},
        RequestContext(request, {}),
    )

def export(request, type):
    """Takes a search query string and builds a gzipped tar archive of the messages
    in the query results.  Two formats are supported: maildir and mbox.
    """
    # force sort order and run query
    data = request.GET.copy()
    data['so'] = 'email_list'
    data['sso'] = 'date'
    form = AdvancedSearchForm(data,load_all=False,request=request)
    sqs = form.search()

    return get_export(sqs, type, request)

def logout_view(request):
    """Logout the user"""
    logout(request)
    return HttpResponseRedirect(reverse('archive'))

def main(request):
    """Main page.  This page contains a simple search form and some links."""
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

