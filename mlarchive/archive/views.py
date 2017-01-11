import json
import re
import os
import urllib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, HttpResponse, Http404, QueryDict
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from haystack.views import SearchView, FacetedSearchView
from haystack.query import SearchQuerySet

from mlarchive.utils.decorators import check_access, superuser_only, pad_id
from mlarchive.archive import actions
from mlarchive.archive.query_utils import get_kwargs
from mlarchive.archive.view_funcs import (initialize_formsets, get_columns, get_export,
    find_message_date, find_message_gbt, get_query_neighbors, is_javascript_disabled,
    get_query_string, get_browse_list)

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
        - subset of results for display (page)
        - selected offset: the offset of message specified in query arguments within
          results subset (page)

        If request arguments include "index", returns slice of results containing
        message named in "index" with appropriate offset within slice, otherwise returns
        first #(results_per_page) messages and offsets=0.
        """
        buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
        index = self.request.GET.get('index')
        try:
            page_no = int(self.request.GET.get('page', 1))
        except ValueError:
            page_no = 1
        # prime slice
        start_offset = (page_no - 1) * self.results_per_page
        self.results[start_offset:start_offset + self.results_per_page + 1]
        paginator = Paginator(self.results, self.results_per_page)
        try:
            self.page = paginator.page(page_no)
        except PageNotAnInteger:
            self.page = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            self.page = paginator.page(paginator.num_pages)

        if index:
            position = self.find_message(index)
            if position == -1:
                raise Http404("No such message!")
            page_no = ( position / self.results_per_page ) + 1
            selected_offset = position % self.results_per_page
            self.page = paginator.page(page_no)
            return (self.page, selected_offset)
        else:
            return (self.page, 0)

    def extra_context(self):
        """Add variables to template context"""
        extra = super(CustomSearchView, self).extra_context()
        query_string = get_query_string(self.request)

        # settings
        extra['FILTER_CUTOFF'] = settings.FILTER_CUTOFF
        extra['browse_list'] = get_browse_list(self.request)
        extra['query_string'] = query_string

        # thread sort
        new_query = self.request.GET.copy()
        if 'gbt' in self.request.GET:
            extra['thread_sorted'] = True
            extra['view_thread_url'] = reverse('archive_search') + query_string
            _ = new_query.pop('gbt')
            extra['view_date_url' ] = reverse('archive_search') + '?' + new_query.urlencode()
        else:
            extra['thread_sorted'] = False
            extra['view_date_url'] = reverse('archive_search') + query_string
            new_query['gbt'] = 1
            extra['view_thread_url'] = reverse('archive_search') + '?' + new_query.urlencode()

        # export links
        extra['export_mbox'] = reverse('archive_export',kwargs={'type':'mbox'}) + query_string
        extra['export_maildir'] = reverse('archive_export',kwargs={'type':'maildir'})+ query_string
        extra['export_url'] = reverse('archive_export',kwargs={'type':'url'})+ query_string

        # modify search link
        if 'as' in self.request.GET:
            extra['modify_search_url'] = reverse('archive_advsearch') + query_string
        else:
            extra['modify_search_url'] = 'javascript:history.back()'
        
        if is_javascript_disabled(self.request):
            extra['modify_search_url'] = None

        # add custom facets
        if hasattr(self,'myfacets'):
            extra['facets'] = self.myfacets

        if hasattr(self,'queryid'):
            extra['queryid'] = self.queryid

        # Pregressive Enhancements.  Start with non-javascript functionality
        extra['no_js'] = True

        # pagination links
        if self.page and self.page.has_other_pages():
            if self.page.has_next():
                new_query = self.request.GET.copy()
                new_query['page'] = self.page.next_page_number()
                extra['next_page_url'] = reverse('archive_search') + '?' + new_query.urlencode()
            if self.page.has_previous():
                new_query = self.request.GET.copy()
                new_query['page'] = self.page.previous_page_number()
                extra['previous_page_url'] = reverse('archive_search') + '?' + new_query.urlencode()
        
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
            return find_message_gbt(self.results,msg,reverse=True)
        elif self.request.GET.get('so') == 'date':
            return find_message_date(self.results,msg)
        else:
            return find_message_date(self.results,msg,reverse=True)

    def create_response(self):
        """
        Generates the actual HttpResponse to send back to the user.
        """
        page, selected_offset = self.build_page()
        
        context = {
            'query': self.query,
            'form': self.form,
            'page': page,
            'count': self.results.count(),
            'suggestion': None,
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
                    results = SearchQuerySet().filter(**kwargs).order_by('id')
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
    NoJSRulesFormset = formset_factory(RulesForm, extra=3)
    nojs_query_formset = NoJSRulesFormset(prefix='nojs-query')
    nojs_not_formset = NoJSRulesFormset(prefix='nojs-not')

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
        'not_formset': not_formset,
        'nojs_query_formset': nojs_query_formset,
        'nojs_not_formset': nojs_not_formset},
        RequestContext(request, {}),
    )

def browse(request, list_name=None):
    """Presents a list of Email Lists the user has access to.  There are
    separate sections for private, active and inactive.
    """
    if list_name:
        redirect_url = '%s?%s' % (reverse('archive_search'), 'email_list=' + list_name)
        return redirect(redirect_url)

    #form = BrowseForm()
    columns = get_columns(request.user)

    if request.method == "GET" and request.GET.get('list'):
        form = BrowseForm(request=request,data=request.GET)
        if form.is_valid():
            params = [('email_list',form.cleaned_data['list'].name)]
            return redirect("%s?%s" % (reverse('archive_search'),urllib.urlencode(params)))
    else:
        form = BrowseForm(request=request)

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
    if 'qid' in request.GET and cache.get(request.GET['qid']):
        queryid = request.GET['qid']
        sqs = cache.get(queryid)
        previous_in_search, next_in_search = get_query_neighbors(
            query = sqs,
            message = msg)
        search_url = reverse('archive_search') + '?' + sqs.query_string

    else:
        previous_in_search = None
        next_in_search = None
        queryid = None
        search_url = None

    return render_to_response('archive/detail.html', {
        'msg':msg,
        # cache items for use in template
        'next_in_list':msg.next_in_list(),
        'next_in_thread':msg.next_in_thread(),
        'next_in_search':next_in_search,
        'previous_in_list':msg.previous_in_list(),
        'previous_in_thread':msg.previous_in_thread(),
        'previous_in_search':previous_in_search,
        'queryid':queryid,
        'replies':msg.replies.all(),
        'references':msg.get_references_messages(),
        'search_url':search_url},
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

def legacy_message(request, list_name, id):
    """Redirect to the appropriate message given list name and legacy number"""
    try:
        message = Message.objects.get(email_list__name=list_name,legacy_number=int(id))
    except Message.DoesNotExist:
        raise Http404("Message not found")
    return HttpResponseRedirect(message.get_absolute_url())

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

