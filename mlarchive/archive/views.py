import datetime
import json
import os
import urllib
from operator import itemgetter

from django.conf import settings
from django.contrib.auth import logout
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from haystack.views import SearchView
from haystack.query import SearchQuerySet
from haystack.forms import SearchForm

from mlarchive.utils.decorators import check_access, superuser_only, pad_id, log_timing
from mlarchive.archive import actions
from mlarchive.archive.query_utils import (get_kwargs, get_cached_query, query_is_listname,
    parse_query_string)
from mlarchive.archive.view_funcs import (initialize_formsets, get_columns, get_export,
    find_message_date, find_message_gbt, get_query_neighbors, is_javascript_disabled,
    get_query_string, get_browse_list, get_lists_for_user)

from models import *
from forms import *

import logging
logger = logging.getLogger('mlarchive.custom')

# --------------------------------------------------
# Classes
# --------------------------------------------------
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
        if query_is_listname(request):
            return redirect(reverse('archive_search') + '?email_list=' + request.GET['q'])
        
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

    @log_timing
    def build_page(self):
        """Returns tuple of:
        - subset of results for display (page)
        - selected offset: the offset of message specified in query arguments within
          results subset (page)

        If request arguments include "index", returns slice of results containing
        message named in "index" with appropriate offset within slice, otherwise returns
        first #(results_per_page) messages and offsets=0.
        """
        
        # if self.request.GET.get('gbt') == '1':
        #    return self.build_page_new()

        # buffer = settings.SEARCH_SCROLL_BUFFER_SIZE
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

    def build_page_new(self):
        """Returns a page of results"""
        results = []
        index = self.request.GET.get('index')
        if self.request.GET.get('gbt') == '1':
            if index:
                message = Message.objects.get(hashcode=index+'=')
                results = [ SearchResult(m) for m in message.thread.message_set.order_by('thread_order') ]

        #assert False, results
        paginator = Paginator(results, self.results_per_page)
        self.page = paginator.page(1)
        return (self.page, message.thread_order)

    def extra_context(self):
        """Add variables to template context"""
        extra = super(CustomSearchView, self).extra_context()
        #assert False, (self.request.META['QUERY_STRING'])
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
            _ = new_query.pop('gbt')  # noqa
            extra['view_date_url' ] = reverse('archive_search') + '?' + new_query.urlencode()
        else:
            extra['thread_sorted'] = False
            extra['view_date_url'] = reverse('archive_search') + query_string
            new_query['gbt'] = 1
            extra['view_thread_url'] = reverse('archive_search') + '?' + new_query.urlencode()

        # export links
        extra['anonymous_export_limit'] = settings.ANONYMOUS_EXPORT_LIMIT
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

        # Progressive Enhancements.  Start with non-javascript functionality
        extra['no_js'] = True

        # pagination links
        if self.page and self.page.has_other_pages():
            if self.page.has_next():
                new_query = self.request.GET.copy()
                new_query['page'] = self.page.next_page_number()
                if 'index' in new_query:
                    new_query.pop('index')
                extra['next_page_url'] = reverse('archive_search') + '?' + new_query.urlencode()
            if self.page.has_previous():
                new_query = self.request.GET.copy()
                new_query['page'] = self.page.previous_page_number()
                if 'index' in new_query:
                    new_query.pop('index')
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

    def get_context(self):
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

        return context

    def get_query(self):
        """
        Returns the query provided by the user.

        Returns an empty string if the query is invalid.
        """
        if self.form.is_valid():
            q = self.form.cleaned_data['q']
            return parse_query_string(q)

        return ''
# --------------------------------------------------
# STANDARD VIEW FUNCTIONS
# --------------------------------------------------
@superuser_only
def admin(request):
    """Administrator View.  Only accessible by the superuser this view allows
    the administrator to run queries and perform actions, ie. remove spam, on the
    results.  Available actions are defined in actions.py
    """
    results = []
    form = AdminForm()
    action_form = AdminActionForm()

    def is_not_whitelisted(search_result):
        if search_result.frm not in whitelist:
            return True
        else:
            return False

    # admin search query
    if request.method == 'GET' and request.GET:
        form = AdminForm(request.GET)
        if form.is_valid():
            kwargs = get_kwargs(form.cleaned_data)
            if kwargs:
                results = SearchQuerySet().filter(**kwargs).order_by('date').load_all()
                if form.cleaned_data.get('exclude_whitelisted_senders'):
                    whitelist = Message.objects.filter(spam_score=-1).values_list('frm',flat=True).distinct()
                    results = filter(is_not_whitelisted, results)

    # perfom action on checked messages
    elif request.method == 'POST':
        action_form = AdminActionForm(request.POST)
        if action_form.is_valid():
            action = action_form.cleaned_data['action']
            func = getattr(actions, action)
            selected = request.POST.getlist('_selected_action')
            queryset = Message.objects.filter(pk__in=selected)
            return func(request, queryset)

    return render(request, 'archive/admin.html', {
        'results': results,
        'form': form,
        'action_form': action_form,
    })

@superuser_only
def admin_console(request):
    weekly_chart_data = get_weekly_data()
    top25_chart_data = get_top25_data()

    return render(request, 'archive/admin_console.html', {
        'last_message': Message.objects.order_by('-pk').first(),
        'weekly_chart_data': mark_safe(json.dumps(weekly_chart_data)),
        'top25_chart_data': mark_safe(json.dumps(top25_chart_data)),
        'message_count': "{:,}".format(Message.objects.count()),
    })

def get_weekly_data():
    '''Returns weekly archive incoming messages'''
    data = []
    start = datetime.datetime.today() - datetime.timedelta(days=365*3)
    start = start.replace(hour=0,second=0, microsecond=0)
    for day in range(156):
        end = start + datetime.timedelta(days=7)
        num = Message.objects.filter(date__gte=start,date__lt=end).count()
        data.append([datetime_to_millis(start),num])
        start = end

    return [{"data":data}]

def datetime_to_millis(date):
    '''Convert a datetime object to Milliseconds since Unix Epoch''' 
    return (date - datetime.datetime(1970,1,1)).total_seconds() * 1000

def get_top25_data():
    '''Returns incoming meesage count for top 25 most active lists'''
    counts = {}
    end = datetime.datetime.today()
    start = end - datetime.timedelta(days=30)
    for message in Message.objects.filter(date__gte=start,date__lt=end).select_related('email_list'):
        name = message.email_list.name
        counts[name] = counts.get(name, 0) + 1
    data = sorted(counts.items(), key=itemgetter(1), reverse=True)[:25]
    return data

@superuser_only
def admin_guide(request):
    return render(request, 'archive/admin_guide.html', {})

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

    return render(request, 'archive/advsearch.html', {
        'form': form,
        'query_formset': query_formset,
        'not_formset': not_formset,
        'nojs_query_formset': nojs_query_formset,
        'nojs_not_formset': nojs_not_formset,
    })

def browse(request, list_name=None):
    """Presents a list of Email Lists the user has access to.  There are
    separate sections for private, active and inactive.
    """
    if list_name:
        redirect_url = '%s?%s' % (reverse('archive_search'), 'email_list=' + list_name)
        return redirect(redirect_url)

    columns = get_columns(request)

    if request.method == "GET" and request.GET.get('list'):
        form = BrowseForm(request=request,data=request.GET)
        if form.is_valid():
            params = [('email_list',form.cleaned_data['list'].name)]
            return redirect("%s?%s" % (reverse('archive_search'),urllib.urlencode(params)))
    else:
        form = BrowseForm(request=request)

    return render(request, 'archive/browse.html', {
        'form': form,
        'columns': columns,
    })

# TODO if we use this, need access decorator
def browse_list(request, list_name):
    """Browse emails by list.  The simple version."""
    list_obj = get_object_or_404(EmailList, name=list_name)

    # default sort order is date descending
    order = request.GET.get('so','-date')
    if not order in ('date','-date','frm','-frm'):
        order = '-date'
    msgs = Message.objects.filter(email_list=list_obj).order_by(order)

    return render(request, 'archive/browse_list.html', {
        'list_obj': list_obj,
        'msgs': msgs,
    })

@pad_id
@check_access
def detail(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    queryid, sqs = get_cached_query(request)
    if sqs:
        previous_in_search, next_in_search = get_query_neighbors(query = sqs,message = msg)
        search_url = reverse('archive_search') + '?' + sqs.query_string
    else:
        previous_in_search = None
        next_in_search = None
        queryid = None
        search_url = None

    return render(request, 'archive/detail.html', {
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
        'search_url':search_url,
    })

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

    return render(request, 'archive/main.html', {
        'form': form,
        'lists': get_lists_for_user(request),
    })

