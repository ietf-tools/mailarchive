from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import json
import os
import re
import urllib
from operator import itemgetter
from collections import namedtuple

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.db.models.query import QuerySet
from django.utils.decorators import method_decorator
from django.forms.formsets import formset_factory
from django.views.generic.detail import DetailView
from django.http import Http404, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, NoReverseMatch
from django.utils.safestring import mark_safe
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django.views.generic import View
from haystack.views import SearchView
from haystack.query import SearchQuerySet
from haystack.forms import SearchForm

from mlarchive.utils.decorators import check_access, superuser_only, pad_id, check_list_access
from mlarchive.archive import actions
from mlarchive.archive.query_utils import (get_kwargs, get_qdr_kwargs, get_cached_query, get_browse_equivalent,
    parse_query_string, get_order_fields, generate_queryid, is_static_on)
from mlarchive.archive.view_funcs import (initialize_formsets, get_columns, get_export,
    get_query_neighbors, get_query_string, get_lists_for_user, get_random_token)

from mlarchive.archive.models import EmailList, Message, Thread, Attachment
from mlarchive.archive.forms import AdminForm, AdminActionForm, AdvancedSearchForm, BrowseForm, RulesForm


THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
DATE_PATTERN = re.compile(r'(?P<year>\d{4})(?:-(?P<month>\d{2}))?')
TimePeriod = namedtuple('TimePeriod', 'year, month')

# --------------------------------------------------
# Helpers
# --------------------------------------------------


def add_nav_urls(context):
    """Update context dictionary with next_page and previous_page urls"""
    if context['group_by_thread']:
        previous_message, next_message = get_thread_endpoints(context['email_list'], context['time_period'])
        next_page = next_message.get_static_thread_page_url() if next_message else ''
        previous_page = previous_message.get_static_thread_page_url() if previous_message else ''
        context.update({'next_page': next_page, 'previous_page': previous_page})
    else:
        previous_message, next_message = get_date_endpoints(context['email_list'], context['time_period'])
        next_page = next_message.get_static_date_page_url() if next_message else ''
        previous_page = previous_message.get_static_date_page_url() if previous_message else ''
        context.update({'next_page': next_page, 'previous_page': previous_page})


def get_thread_endpoints(email_list, time_period):
    """Returns previous top thread message before time_period, and next message after time_period
    for given list
    """
    this_period, next_period = get_this_next_periods(time_period)
    next_thread = email_list.thread_set.filter(date__gte=next_period).order_by('date').first()
    next_message = next_thread.first if next_thread else None
    previous_thread = email_list.thread_set.filter(date__lt=this_period).order_by('date').last()
    previous_message = previous_thread.first if previous_thread else None
    return (previous_message, next_message)


def get_date_endpoints(email_list, time_period):
    """Returns previous message before time_period, and next message after time_period
    for given list
    """
    this_period, next_period = get_this_next_periods(time_period)
    next_message = email_list.message_set.filter(date__gte=next_period).order_by('date').first()
    previous_message = email_list.message_set.filter(date__lt=this_period).order_by('date').last()
    return (previous_message, next_message)


def get_this_next_periods(time_period):
    """Given a time_period tuple, returns a tuple of the first date in that period and
    the first date in the next period, where period is a month or year, based
    on the string provided.  For example, 2017-04 returns the dates:
    (datetime(2017,4,1), datetime(2017,5,1))
    """
    if time_period.month:
        this_period = datetime.datetime(time_period.year, time_period.month, 1)
        next_period = add_one_month(this_period)
    else:
        this_period = datetime.datetime(time_period.year, 1, 1)
        next_period = this_period + datetime.timedelta(days=365)
    return (this_period, next_period)


def add_one_month(dt0):
    dt1 = dt0.replace(day=1)
    dt2 = dt1 + datetime.timedelta(days=32)
    dt3 = dt2.replace(day=1)
    return dt3


def is_small_year(email_list, year):
    count = Message.objects.filter(email_list=email_list, date__year=year).count()
    return count < settings.STATIC_INDEX_YEAR_MINIMUM


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
        browse_list = get_browse_equivalent(request)
        if browse_list:
            try:
                if is_static_on(request):
                    return redirect('archive_browse_static', list_name=browse_list)
                else:
                    return redirect('archive_browse_list', list_name=browse_list)
            except NoReverseMatch:
                raise Http404("Invalid List")

        self.base_url = reverse('archive_search')
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
        token = get_random_token(length=16)
        new_query = self.request.GET.copy()
        new_query['token'] = token
        extra['export_token'] = token
        extra['anonymous_export_limit'] = settings.ANONYMOUS_EXPORT_LIMIT
        extra['export_limit'] = settings.EXPORT_LIMIT
        extra['export_mbox'] = reverse('archive_export', kwargs={'type': 'mbox'}) + '?' + new_query.urlencode()
        extra['export_maildir'] = reverse('archive_export', kwargs={'type': 'maildir'}) + '?' + new_query.urlencode()
        extra['export_url'] = reverse('archive_export', kwargs={'type': 'url'}) + '?' + new_query.urlencode()

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
            extra['view_thread_url'] = self.base_url + extra['query_string']
            new_query.pop('gbt')
            extra['view_date_url'] = self.base_url + '?' + new_query.urlencode()
        else:
            extra['view_date_url'] = self.base_url + extra['query_string']
            new_query['gbt'] = 1
            extra['view_thread_url'] = self.base_url + '?' + new_query.urlencode()

    def set_page_links(self, extra):
        if self.page and self.page.has_other_pages():
            if self.page.has_next():
                new_query = self.request.GET.copy()
                new_query['page'] = self.page.next_page_number()
                if 'index' in new_query:
                    new_query.pop('index')
                extra['next_page_url'] = self.base_url + '?' + new_query.urlencode()
            if self.page.has_previous():
                new_query = self.request.GET.copy()
                new_query['page'] = self.page.previous_page_number()
                if 'index' in new_query:
                    new_query.pop('index')
                extra['previous_page_url'] = self.base_url + '?' + new_query.urlencode()

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
        if is_static_on(request):
            return redirect('archive_browse_static', list_name=list_name)

        self.base_url = reverse('archive_browse_list', kwargs={'list_name': list_name})
        self.list_name = list_name
        self.email_list = email_list
        self.kwargs = {}

        self.request = request
        self.form = self.build_form()
        self.query = self.get_query()
        self.results = self.get_results()
        if hasattr(self.results, 'myfacets'):
            self.myfacets = self.results.myfacets
        if hasattr(self.results, 'queryid'):
            self.queryid = self.results.queryid

        return self.create_response()

    def get_results(self):
        """Gets a small set of results from the database rather than the search index"""
        if self.query:
            return self.form.search(email_list=self.email_list)

        fields = get_order_fields(self.request.GET, use_db=True)
        results = self.email_list.message_set.order_by(*fields)
        self.kwargs = get_qdr_kwargs(self.request.GET)
        if self.kwargs:
            results = results.filter(**self.kwargs)

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
        extra['queryset_offset'] = '0'
        if self.query or self.kwargs:
            if isinstance(self.results, QuerySet):
                extra['count'] = self.results.count()
            else:
                extra['count'] = len(self.results)
        else:
            extra['count'] = Message.objects.filter(email_list__name=self.list_name).count()

        # export links
        token = get_random_token(length=16)
        new_query = self.request.GET.copy()
        new_query['email_list'] = self.list_name
        new_query['token'] = token
        extra['export_token'] = token
        extra['export_limit'] = settings.EXPORT_LIMIT
        extra['export_mbox'] = reverse('archive_export', kwargs={'type': 'mbox'}) + '?' + new_query.urlencode()
        extra['export_maildir'] = reverse('archive_export', kwargs={'type': 'maildir'}) + '?' + new_query.urlencode()
        extra['export_url'] = reverse('archive_export', kwargs={'type': 'url'}) + '?' + new_query.urlencode()

        extra['static_off_url'] = reverse('archive_browse_list', kwargs={'list_name': self.list_name})
        extra['static_on_url'] = reverse('archive_browse_static', kwargs={'list_name': self.list_name})

        return extra


@method_decorator(check_list_access, name='dispatch')
class BaseStaticIndexView(View):
    list_name = None
    date = None
    email_list = None
    year_filter = None
    month_filter = None
    queryset = None
    month = None
    year = None

    def get_filters(self):
        """Returns dictionary of Queryset filters based on datestring YYYY or YYYY-MM"""
        filters = {'date__year': self.year}
        if self.month:
            filters['date__month'] = self.month
        return filters

    def get_month_year(self, date):
        match = DATE_PATTERN.match(date)
        if match:
            year = int(match.groupdict()['year'])
            month = match.groupdict()['month']
            if month:
                month = int(month)
        else:
            raise Http404("Invalid URL")

        return month, year

    def get_date_string(self):
        if self.month:
            date = datetime.datetime(self.year, self.month, 1)
            return date.strftime('%b %Y')
        else:
            date = datetime.datetime(self.year, 1, 1)
            return date.strftime('%Y')

    def get_client_side_redirect(self):
        current_year = datetime.datetime.today().year
        if self.month and self.year < current_year and is_small_year(self.kwargs['email_list'], self.year):
            url = reverse(self.view_name, kwargs={'list_name': self.kwargs['list_name'], 'date': self.year})
            return render(self.request, 'archive/refresh.html', {'url': url})

        if not self.month and self.queryset.count() > 0 and (self.year == current_year or not is_small_year(self.kwargs['email_list'], self.year)):
            date = self.queryset.last().date
            url = reverse(self.view_name, kwargs={'list_name': self.kwargs['list_name'], 'date': '{}-{:02d}'.format(date.year, date.month)})
            return render(self.request, 'archive/refresh.html', {'url': url})

    def get_context_data(self):
        is_static_on = True if self.request.COOKIES.get('isStaticOn') == 'true' else False
        context = dict(static_mode_on=is_static_on,
                       email_list=self.kwargs['email_list'],
                       queryset=self.queryset,
                       group_by_thread=self.group_by_thread,
                       time_period=TimePeriod(year=self.year, month=self.month),
                       date_string=self.get_date_string(),
                       static_off_url=reverse('archive_browse_list', kwargs={'list_name': self.kwargs['list_name']}))

        add_nav_urls(context)
        return context

    def render_to_response(self, context):
        response = render(self.request, 'archive/static_index_date.html', context)
        if self.kwargs['email_list'].private:
            add_never_cache_headers(response)
        else:
            patch_cache_control(response, max_age=settings.CACHE_CONTROL_MAX_AGE)
        return response

    def get(self, request, **kwargs):
        self.kwargs['email_list'] = kwargs['email_list']    # this was added by decorator
        self.month, self.year = self.get_month_year(kwargs['date'])
        self.filters = self.get_filters()
        if self.group_by_thread:
            # two-step query to avoid inefficient INNER JOIN
            self.filters['email_list'] = self.kwargs['email_list']
            threads = [t.id for t in Thread.objects.filter(**self.filters)]
            self.queryset = kwargs['email_list'].message_set.filter(thread_id__in=threads).order_by(*self.order_fields)

        else:
            self.queryset = kwargs['email_list'].message_set.filter(**self.filters).order_by(*self.order_fields)

        redirect = self.get_client_side_redirect()
        if redirect:
            return redirect

        context = self.get_context_data()
        return self.render_to_response(context)


class DateStaticIndexView(BaseStaticIndexView):
    order_fields = ['-date']
    view_name = 'archive_browse_static_date'
    group_by_thread = False


class ThreadStaticIndexView(BaseStaticIndexView):
    order_fields = settings.THREAD_ORDER_FIELDS
    view_name = 'archive_browse_static_thread'
    group_by_thread = True


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


@pad_id
@check_access
def attachment(request, list_name, id, sequence, msg):
    try:
        attachment = msg.attachment_set.get(sequence=sequence)
    except Attachment.DoesNotExist:
        raise Http404("Attachment not found")

    sub_message = attachment.get_sub_message()
    payload = sub_message.get_payload(decode=True)
    response = HttpResponse(payload, content_type=attachment.content_type)
    response['Content-Disposition'] = 'attachment; filename=%s' % attachment.name
    return response


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
    is_static_on = True if request.COOKIES.get('isStaticOn') == 'true' else False
    columns = get_columns(request)

    if request.method == "GET" and request.GET.get('list'):
        form = BrowseForm(request=request, data=request.GET)
        if form.is_valid():
            list_name = form.cleaned_data['list'].name
            params = [('email_list', list_name)]
            if is_static_on:
                return redirect('/arch/browse/{name}/index.html'.format(name=list_name))
            else:
                return redirect('{url}?{params}'.format(url=reverse('archive_search'), params=urllib.urlencode(params)))
    else:
        form = BrowseForm(request=request)

    return render(request, 'archive/browse.html', {
        'form': form,
        'columns': columns,
    })


def browse_static_redirect(request, list_name):
    email_list = get_object_or_404(EmailList, name=list_name)
    last_message = email_list.message_set.order_by('-date').first()
    return redirect(last_message.get_static_date_page_url())


def browse_static_thread_redirect(request, list_name):
    email_list = get_object_or_404(EmailList, name=list_name)
    last_message = email_list.message_set.order_by('-date').first()
    return redirect(last_message.get_static_thread_page_url())


@pad_id
@check_access
def detail(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    is_static_on = True if request.COOKIES.get('isStaticOn') == 'true' else False
    queryid, sqs = get_cached_query(request)

    if sqs and not is_static_on:
        previous_in_search, next_in_search = get_query_neighbors(query=sqs, message=msg)
        search_url = reverse('archive_search') + '?' + sqs.query_string
    else:
        previous_in_search = None
        next_in_search = None
        queryid = None
        search_url = None

    response = render(request, 'archive/detail.html', {
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

    if msg.email_list.private:
        add_never_cache_headers(response)
    return response


# removed login requirement until API is created
# @login_required
def export(request, type):
    """Takes a search query string and builds a gzipped tar archive of the messages
    in the query results.
    """
    # force sort order and run query
    data = request.GET.copy()
    data['so'] = 'email_list'
    data['sso'] = 'date'
    form = AdvancedSearchForm(data, load_all=False, request=request)
    sqs = form.search()
    count = sqs.count()
    response = get_export(sqs, type, request)
    if data.get('token'):
        response.set_cookie('downloadToken', data.get('token'))
    return response


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
        'lists': get_lists_for_user(request.user),
    })


class MessageDetailView(DetailView):

    model = Message


@pad_id
@check_access
def detailx(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    is_static_on = True if request.COOKIES.get('isStaticOn') == 'true' else False
    queryid, sqs = get_cached_query(request)

    if sqs and not is_static_on:
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
