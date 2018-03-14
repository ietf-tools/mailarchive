import datetime
import json
import os
import urllib
from operator import itemgetter

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.forms.formsets import formset_factory
from django.views.generic.detail import DetailView
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from haystack.views import SearchView
from haystack.query import SearchQuerySet
from haystack.forms import SearchForm

from mlarchive.utils.decorators import check_access, superuser_only, pad_id, log_timing, check_list_access
from mlarchive.archive import actions
from mlarchive.archive.query_utils import (get_kwargs, get_cached_query, query_is_listname,
    parse_query_string, get_order_fields, generate_queryid)
from mlarchive.archive.view_funcs import (initialize_formsets, get_columns, get_export,
    get_query_neighbors, get_query_string, get_lists_for_user)

from models import EmailList, Message
from forms import AdminForm, AdminActionForm, AdvancedSearchForm, BrowseForm, RulesForm

import logging
logger = logging.getLogger('mlarchive.custom')


# --------------------------------------------------
# Classes
# --------------------------------------------------

class CustomSearchView(SearchView):
    """A customized SearchView"""

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
            return redirect('archive_browse_list', list_name=request.GET['q'])

        self.request = request
        self.form = self.build_form()
        self.query = self.get_query()
        self.results = self.get_results()
        if hasattr(self.results, 'myfacets'):
            self.myfacets = self.results.myfacets
        if hasattr(self.results, 'queryid'):
            self.queryid = self.results.queryid

        return self.create_response()

    def build_form(self, form_kwargs=None):
        """Add request object to the form init so we can use it for authorization"""
        return super(CustomSearchView, self).build_form(form_kwargs={'request': self.request})

    def extra_context(self):
        """Add variables to template context"""
        extra = super(CustomSearchView, self).extra_context()
        query_string = get_query_string(self.request)

        # settings
        extra['filter_cutoff'] = settings.FILTER_CUTOFF
        extra['query_string'] = query_string
        extra['results_per_page'] = settings.HAYSTACK_SEARCH_RESULTS_PER_PAGE
        extra['queryset_offset'] = str(self.page.start_index() - 1)
        # Review
        if isinstance(self.results, list):
            extra['count'] = len(self.results)
        else:
            extra['count'] = self.results.count()

        # export links
        extra['anonymous_export_limit'] = settings.ANONYMOUS_EXPORT_LIMIT
        extra['export_mbox'] = reverse('archive_export', kwargs={'type': 'mbox'}) + query_string
        extra['export_maildir'] = reverse('archive_export', kwargs={'type': 'maildir'}) + query_string
        extra['export_url'] = reverse('archive_export', kwargs={'type': 'url'}) + query_string

        # modify search link
        if 'as' in self.request.GET:
            extra['modify_search_url'] = reverse('archive_advsearch') + query_string
        else:
            extra['modify_search_url'] = 'javascript:history.back()'

        # add custom facets
        if hasattr(self, 'myfacets'):
            extra['facets'] = self.myfacets

        if hasattr(self, 'queryid'):
            extra['queryid'] = self.queryid

        self.set_thread_links(extra)
        self.set_page_links(extra)

        return extra

    def set_thread_links(self, extra):
        extra['group_by_thread'] = True if 'gbt' in self.request.GET else False
        new_query = self.request.GET.copy()

        if extra['group_by_thread']:
            extra['view_thread_url'] = reverse('archive_search') + extra['query_string']
            new_query.pop('gbt')
            extra['view_date_url'] = reverse('archive_search') + '?' + new_query.urlencode()
        else:
            extra['view_date_url'] = reverse('archive_search') + extra['query_string']
            new_query['gbt'] = 1
            extra['view_thread_url'] = reverse('archive_search') + '?' + new_query.urlencode()

    def set_page_links(self, extra):
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

    def get_context(self):
        # page, selected_offset = self.build_page()
        self.paginator, self.page = self.build_page()

        context = {
            'query': self.query,
            'form': self.form,
            'page': self.page,
            'selected_offset': None,
        }

        context.update(self.extra_context())

        return context

    def get_query(self):
        if self.form.is_valid():
            q = self.form.cleaned_data['q']
            return parse_query_string(q)

        return ''


@method_decorator(check_list_access, name='__call__')
class CustomBrowseView(CustomSearchView):
    """A customized SearchView for browsing a list"""
    def __name__(self):
        return "CustomBrowseView"

    def __call__(self, request, list_name, email_list):
        is_legacy_on = True if request.COOKIES.get('isLegacyOn') == 'true' else False
        if is_legacy_on:
            return redirect('./maillist.html')

        self.list_name = list_name
        self.email_list = email_list
        return super(CustomBrowseView, self).__call__(request)

    def get_results(self):
        """Gets a small set of results from the database rather than the search index"""
        if self.query:
            return self.form.search(email_list=self.email_list)

        fields = get_order_fields(self.request.GET, use_db=True)
        results = self.email_list.message_set.order_by(*fields)

        self.index = self.request.GET.get('index')
        if self.index:
            try:
                index_message = Message.objects.get(email_list=self.email_list, hashcode=self.index + '=')
            except Message.DoesNotExist:
                raise Http404("No such message!")

            if 'gbt' in self.request.GET:
                results = []
                thread = index_message.thread
                while len(results) < self.results_per_page and thread:
                    results.extend(thread.message_set.order_by('thread_order'))
                    thread = thread.get_previous()  # default ordering is descending by thread date
            else:
                results = Message.objects.filter(
                    email_list=self.email_list,
                    date__lte=index_message.date).order_by('-date').select_related()[:self.results_per_page]

        return results

    def extra_context(self):
        """Add variables to template context"""
        extra = super(CustomBrowseView, self).extra_context()
        extra['browse_list'] = self.list_name
        extra['queryset_offset'] = '200'
        if self.query:
            extra['count'] = self.results.count()
        else:
            extra['count'] = Message.objects.filter(email_list__name=self.list_name).count()

        # export links
        new_query = self.request.GET.copy()
        new_query['email_list'] = self.list_name
        extra['export_mbox'] = reverse('archive_export', kwargs={'type': 'mbox'}) + '?' + new_query.urlencode()
        extra['export_maildir'] = reverse('archive_export', kwargs={'type': 'maildir'}) + '?' + new_query.urlencode()
        extra['export_url'] = reverse('archive_export', kwargs={'type': 'url'}) + '?' + new_query.urlencode()

        return extra

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
                    whitelist = Message.objects.filter(spam_score=-1).values_list('frm', flat=True).distinct()
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
    start = datetime.datetime.today() - datetime.timedelta(days=365 * 3)
    start = start.replace(hour=0, second=0, microsecond=0)
    for day in range(156):
        end = start + datetime.timedelta(days=7)
        num = Message.objects.filter(date__gte=start, date__lt=end).count()
        data.append([datetime_to_millis(start), num])
        start = end

    return [{"data": data}]


def datetime_to_millis(date):
    '''Convert a datetime object to Milliseconds since Unix Epoch'''
    return (date - datetime.datetime(1970, 1, 1)).total_seconds() * 1000


def get_top25_data():
    '''Returns incoming meesage count for top 25 most active lists'''
    counts = {}
    end = datetime.datetime.today()
    start = end - datetime.timedelta(days=30)
    for message in Message.objects.filter(date__gte=start, date__lt=end).select_related('email_list'):
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
        form = AdvancedSearchForm(request=request, initial=request.GET)
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


def browse(request):
    """Presents a list of Email Lists the user has access to.  There are
    separate sections for private, active and inactive.
    """
    is_legacy_on = True if request.COOKIES.get('isLegacyOn') == 'true' else False
    columns = get_columns(request)

    if request.method == "GET" and request.GET.get('list'):
        form = BrowseForm(request=request, data=request.GET)
        if form.is_valid():
            list_name = form.cleaned_data['list'].name
            params = [('email_list', list_name)]
            if is_legacy_on:
                return redirect('/arch/browse/{name}/index.html'.format(name=list_name))
            else:
                return redirect('{url}?{params}'.format(url=reverse('archive_search'), params=urllib.urlencode(params)))
    else:
        form = BrowseForm(request=request)

    return render(request, 'archive/browse.html', {
        'form': form,
        'columns': columns,
    })


@pad_id
@check_access
def detail(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    is_legacy_on = True if request.COOKIES.get('isLegacyOn') == 'true' else False
    queryid, sqs = get_cached_query(request)

    if sqs and not is_legacy_on:
        previous_in_search, next_in_search = get_query_neighbors(query=sqs, message=msg)
        search_url = reverse('archive_search') + '?' + sqs.query_string
    else:
        previous_in_search = None
        next_in_search = None
        queryid = None
        search_url = None

    return render(request, 'archive/detail.html', {
        'msg': msg,
        # cache items for use in template
        'next_in_list': msg.next_in_list(),
        'next_in_thread': msg.next_in_thread(),
        'next_in_search': next_in_search,
        'previous_in_list': msg.previous_in_list(),
        'previous_in_thread': msg.previous_in_thread(),
        'previous_in_search': previous_in_search,
        'queryid': queryid,
        'search_url': search_url,
    })


def export(request, type):
    """Takes a search query string and builds a gzipped tar archive of the messages
    in the query results.  Two formats are supported: maildir and mbox.
    """
    # force sort order and run query
    data = request.GET.copy()
    data['so'] = 'email_list'
    data['sso'] = 'date'
    form = AdvancedSearchForm(data, load_all=False, request=request)
    sqs = form.search()

    return get_export(sqs, type, request)


def legacy_message(request, list_name, id):
    """Redirect to the appropriate message given list name and legacy number"""
    try:
        message = Message.objects.get(email_list__name=list_name, legacy_number=int(id))
    except Message.DoesNotExist:
        raise Http404("Message not found")
    return redirect(message)


def logout_view(request):
    """Logout the user"""
    logout(request)
    return redirect('archive')


def main(request):
    """Main page.  This page contains a simple search form and some links."""
    if request.GET:
        form = SearchForm(request.GET)
    else:
        form = SearchForm()

    if os.path.exists(settings.LOG_FILE):
        try:
            os.chmod(settings.LOG_FILE, 0666)
        except OSError:
            pass

    return render(request, 'archive/main.html', {
        'form': form,
        'lists': get_lists_for_user(request),
    })


class MessageDetailView(DetailView):

    model = Message


@pad_id
@check_access
def detailx(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    is_legacy_on = True if request.COOKIES.get('isLegacyOn') == 'true' else False
    queryid, sqs = get_cached_query(request)

    if sqs and not is_legacy_on:
        previous_in_search, next_in_search = get_query_neighbors(query=sqs, message=msg)
        search_url = reverse('archive_search') + '?' + sqs.query_string
    else:
        previous_in_search = None
        next_in_search = None
        queryid = None
        search_url = None

    return render(request, 'archive/detail.html', {
        'msg': msg,
        # cache items for use in template
        'next_in_list': '',
        'next_in_thread': '',
        'next_in_search': '',
        'previous_in_list': '',
        'previous_in_thread': '',
        'previous_in_search': '',
        'queryid': queryid,
        'search_url': search_url,
    })