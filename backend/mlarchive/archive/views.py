import csv
import datetime
import functools
import json
import os
import re
from operator import itemgetter
from collections import namedtuple, Counter
from datetime import timezone
from dateutil.relativedelta import relativedelta
from dateutil.parser import isoparse

from csp.decorators import csp_exempt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import InvalidPage
from django.forms.formsets import formset_factory
from django.views.generic.detail import DetailView
from django.views.generic.base import TemplateView
from django.http import Http404, HttpResponse, QueryDict
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, NoReverseMatch
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django.views.generic import View

from elasticsearch.exceptions import RequestError

from mlarchive.utils.decorators import (check_access, superuser_only, pad_id, 
    check_list_access, staff_only)
from mlarchive.archive import actions
from mlarchive.archive.backends.elasticsearch import search_from_form
from mlarchive.archive.query_utils import (get_qdr_kwargs,
    get_cached_query, get_browse_equivalent, parse_query_string, get_order_fields,
    is_static_on, get_count, CustomPaginator)
from mlarchive.archive.view_funcs import (initialize_formsets, get_columns, get_export,
    get_query_neighbors, get_query_string, get_lists_for_user, get_random_token)

from mlarchive.archive.models import (EmailList, Message, Thread, Attachment,
    Subscriber)
from mlarchive.archive.forms import (AdminForm, AdminActionForm, 
    AdvancedSearchForm, BrowseForm, RulesForm, SearchForm, DateForm)

import logging
logger = logging.getLogger(__name__)

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
        this_period = datetime.datetime(time_period.year, time_period.month, 1, tzinfo=timezone.utc)
        next_period = this_period + relativedelta(months=1)
    else:
        this_period = datetime.datetime(time_period.year, 1, 1, tzinfo=timezone.utc)
        next_period = this_period + relativedelta(years=1)
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
# Mixins
# --------------------------------------------------


class CSVResponseMixin(object):
    """
    A generic mixin that constructs a CSV response from 'object_list'
    in the the context data if the CSV export option was provided in
    the request. 'object_list' can be a list of Django models or
    a list of named tuples.
    NOTE: use attribute csv_fields to specify which object fields to 
    include, else all fields.
    """
    def recursive_getattr(self, obj, attr, *args):
        def _getattr(obj, attr):
            attribute = getattr(obj, attr, *args)
            if hasattr(attribute, 'strftime'):
                return attribute.strftime("%Y-%m-%d %H:%M:%S")
            else:
                return attribute
        return functools.reduce(_getattr, [obj] + attr.split('.'))

    def get_csv_headers(self, obj):
        if hasattr(self, 'csv_fields'):
            return [field.split('.')[-1] for field in self.csv_fields]
        elif hasattr(obj, '_fields'):
            return obj._fields
        else:
            return []

    def get_csv_row(self, obj):
        """
        Returns a list of values to write a csv row
        """
        if hasattr(self, 'csv_fields'):
            return [self.recursive_getattr(obj, field) for field in self.csv_fields]
        # from Django model
        elif hasattr(self, 'model'):
            meta = self.model._meta
            field_names = [field.name for field in meta.fields]
            return [getattr(obj, field) for field in field_names]
        # from namedtuple
        elif hasattr(obj, '_fields'):
            return [getattr(obj, field) for field in obj._fields]
        else:
            return []

    def get_csv_url(self, **kwargs):
        path_info = self.request.META['PATH_INFO']
        query = self.request.META['QUERY_STRING']
        querydict = QueryDict(query, mutable=True)
        querydict['export'] = 'csv'
        query_string = querydict.urlencode()
        csv_url = f'{path_info}?{query_string}'
        return csv_url

    def render_to_response(self, context, **response_kwargs):
        """
        Creates a CSV response if requested, otherwise returns the default
        template response.
        """
        # Sniff if we need to return a CSV export
        if 'csv' in self.request.GET.get('export', ''):
            response = HttpResponse(content_type='text/csv')
            filename = 'export.csv'
            response['Content-Disposition'] = 'attachment; filename="%s"' % filename

            writer = csv.writer(response)
            
            # empty list
            if len(context['object_list']) == 0:
                writer.writerow(['empty list'])
                return response
            
            # write headers
            writer.writerow(self.get_csv_headers(context['object_list'][0]))
            for obj in context['object_list']:
                writer.writerow(self.get_csv_row(obj))

            return response
        # Business as usual otherwise
        else:
            return super().render_to_response(context, **response_kwargs)


# --------------------------------------------------
# Classes
# --------------------------------------------------

class CustomSearchView(View):
    """A customized SearchView"""
    template = 'archive/search.html'
    extra_context = {}
    form_class = AdvancedSearchForm
    query = ''
    results = None      # EmptySearchQuerySet()
    request = None
    form = None
    results_per_page = settings.ELASTICSEARCH_RESULTS_PER_PAGE

    def get(self, request):
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
        
        # get search object
        self.search = search_from_form(self.form)
        if hasattr(self.search, 'queryid'):
            self.queryid = self.search.queryid

        return self.create_response()

    def build_form(self, form_kwargs=None):
        """Add request object to the form init so we can use it for authorization"""
        data = None
        kwargs = {'request': self.request}
        if form_kwargs:
            kwargs.update(form_kwargs)

        if len(self.request.GET):
            data = self.request.GET

        return self.form_class(data, **kwargs)

    def extra_context(self):
        """Add variables to template context"""
        self.results = self.page.object_list    # create a synonym 
        extra = {}
        query_string = get_query_string(self.request)

        # settings
        extra['filter_cutoff'] = settings.FILTER_CUTOFF
        extra['query_string'] = query_string
        extra['results_per_page'] = settings.ELASTICSEARCH_RESULTS_PER_PAGE
        extra['queryset_offset'] = str(self.page.start_index() - 1)
        extra['count'] = get_count(self.search)

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
            extra['modify_search_url'] = reverse('archive')

        # add custom facets
        if hasattr(self.results, 'aggregations'):
            extra['aggregations'] = self.results.aggregations

        if hasattr(self, 'queryid'):
            extra['queryid'] = self.queryid

        self.set_thread_links(extra)
        self.set_page_links(extra)

        return extra

    '''
    def get_results(self):
        """
        Gets the search object from the form. Executes search.

        Returns an empty list if there's no query to search with.
        """
        # self.search = self.form.search()
        
        # save custom attributes
        if hasattr(self.search, 'queryid'):
            self.queryid = self.search.queryid

        self.response = run_query(self.search)
        return self.response
    '''

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
        self.paginator, self.page = self.build_page()

        context = {
            'query': self.query,
            'form': self.form,
            'page': self.page,
            'selected_offset': None,
        }

        context.update(self.extra_context())

        return context

    def build_page(self):
        """
        Paginates the results appropriately.
        """
        try:
            page_no = int(self.request.GET.get('page', 1))
        except (TypeError, ValueError):
            raise Http404("Not a valid number for page.")

        if page_no < 1:
            raise Http404("Pages should be 1 or greater.")

        paginator = CustomPaginator(self.search, self.results_per_page)

        try:
            page = paginator.page(page_no)
        except InvalidPage:
            raise Http404("No such page!")

        return (paginator, page)

    def get_query(self):
        if self.form.is_valid():
            q = self.form.cleaned_data['q']
            return parse_query_string(q)

        return ''

    def create_response(self):
        """
        Generates the actual HttpResponse to send back to the user.

        There are various places where the Elasticsearch object is 
        evaluated and my raise an exception RequestError (within the
        paginator when calling count() for example) Catch this exception
        and redirect to main page.)
        """
        try:
            context = self.get_context()
        except RequestError as error:
            logger.info(error)
            messages.error(self.request, 'Invalid search expression')
            return redirect('archive')

        return render(self.request, self.template, context)


@method_decorator(check_list_access, name='dispatch')
class CustomBrowseView(CustomSearchView):
    """A customized SearchView for browsing a list"""

    def get(self, request, *args, **kwargs):
        if 'list_name' in kwargs:
            self.list_name = kwargs['list_name']
        if 'email_list' in kwargs:
            self.email_list = kwargs['email_list']
            
        if is_static_on(request):
            return redirect('archive_browse_static', list_name=self.list_name)

        self.base_url = reverse('archive_browse_list', kwargs={'list_name': self.list_name})
        self.kwargs = {}
        self.request = request
        self.form = self.build_form()
        self.query = self.get_query()
        self.search = self.get_search()

        return self.create_response()

    def get_search(self):
        """If there is a search query build an Elasticsearch search object and 
        return that. Otherwise build an ORM Message query and return that"""
        # Elasticsearch query
        if self.query:
            search = search_from_form(self.form, email_list=self.email_list)
            if hasattr(search, 'queryid'):
                self.queryid = search.queryid
            return search

        # DB Query
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
        extra = {}
        query_string = get_query_string(self.request)

        # settings
        extra['query_string'] = query_string
        extra['browse_list'] = self.list_name
        extra['browse_list_placeholder'] = 'Search {}'.format(self.list_name)
        extra['queryset_offset'] = '0'
        extra['count'] = get_count(self.search)

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

        if hasattr(self, 'queryid'):
            extra['queryid'] = self.queryid

        self.set_thread_links(extra)
        self.set_page_links(extra)

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

        if not self.month and get_count(self.queryset) > 0 and (self.year == current_year or not is_small_year(self.kwargs['email_list'], self.year)):
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
        response = render(self.request, 'archive/static_index.html', context)
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
    form = AdminForm(request=request)
    action_form = AdminActionForm()

    # def is_not_whitelisted(search_result):
    #     if search_result.frm not in whitelist:
    #         return True
    #     else:
    #         return False

    # admin search query
    if request.method == 'GET' and request.GET:
        form = AdminForm(request.GET, request=request)
        if not request.GET:
            results = []

        elif form.is_valid():
            search = search_from_form(form)
            logger.debug('admin query: {}'.format(search.to_dict()))
            # TODO change in v7
            # search = search.sort('-date')    # default sort by date descending
            # results = list(search.scan(preserve_order=True))   # convert to list for tests
            results = list(search.scan())   # convert to list for tests
            results = sorted(results, key=lambda h: h.date, reverse=True)
            # if form.cleaned_data.get('exclude_whitelisted_senders'):
            #     whitelist = Message.objects.filter(spam_score=-1).values_list('frm', flat=True).distinct()
            #     results = list(filter(is_not_whitelisted, results))

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


@csp_exempt
@staff_member_required
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
    start = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=365 * 3)
    start = start.replace(hour=0, second=0, microsecond=0)
    for day in range(156):
        end = start + datetime.timedelta(days=7)
        num = Message.objects.filter(date__gte=start, date__lt=end).count()
        data.append([datetime_to_millis(start), num])
        start = end

    return [{"data": data}]


def datetime_to_millis(date):
    '''Convert a datetime object to Milliseconds since Unix Epoch'''
    return (date - datetime.datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1000


def get_top25_data():
    '''Returns incoming message count for top 25 most active lists'''
    counts = {}
    end = datetime.datetime.now(timezone.utc)
    start = end - datetime.timedelta(days=30)
    for message in Message.objects.filter(date__gte=start, date__lt=end).select_related('email_list'):
        name = message.email_list.name
        counts[name] = counts.get(name, 0) + 1
    data = sorted(list(counts.items()), key=itemgetter(1), reverse=True)[:25]
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
    """Advanced Search View

    Presents an extendable search form. Javascript converts
    field queries to a text input 'q' field. For example:
    text:(database)

    The form is submitted to the search view
    """
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


def browse(request, force_static=False):
    """Presents a list of Email Lists the user has access to.  There are
    separate sections for private, active and inactive.
    """
    is_static_on = True if request.COOKIES.get('isStaticOn') == 'true' else False
    columns = get_columns(request)

    if request.method == "GET" and request.GET.get('list'):
        form = BrowseForm(request=request, data=request.GET)
        if form.is_valid():
            list_name = form.cleaned_data['list'].name
            if is_static_on:
                url = reverse('archive_browse_static', kwargs={'list_name': list_name})
                return redirect(url)
            else:
                url = reverse('archive_browse_list', kwargs={'list_name': list_name})
                return redirect(url)
    else:
        form = BrowseForm(request=request)

    return render(request, 'archive/browse.html', {
        'form': form,
        'columns': columns,
        'force_static': force_static,
        'is_static_on': is_static_on,
    })


def browse_static(request):
    """Browse with links to static pages"""
    return browse(request, force_static=True)


def browse_static_redirect(request, list_name):
    email_list = get_object_or_404(EmailList, name=list_name)
    last_message = email_list.message_set.order_by('-date').first()
    if last_message:
        return redirect(last_message.get_static_date_page_url())
    else:
        return redirect('archive_browse_static_date', list_name=list_name, date=datetime.datetime.now(timezone.utc).year)


def browse_static_thread_redirect(request, list_name):
    email_list = get_object_or_404(EmailList, name=list_name)
    last_message = email_list.message_set.order_by('-date').first()
    if last_message:
        return redirect(last_message.get_static_thread_page_url())
    else:
        return redirect('archive_browse_static_thread', list_name=list_name, date=datetime.datetime.now(timezone.utc).year)


@pad_id
@check_access
def detail(request, list_name, id, msg):
    """Displays the requested message.
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    is_static_on = True if request.COOKIES.get('isStaticOn') == 'true' else False
    queryid, search = get_cached_query(request)

    if search and not is_static_on:
        previous_in_search, next_in_search = get_query_neighbors(search=search, message=msg)
    else:
        previous_in_search = None
        next_in_search = None
        queryid = None

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
    form = AdvancedSearchForm(data, request=request)
    search = search_from_form(form, skip_facets=True)
    try:
        response = get_export(search, type, request)
    except RequestError as error:
        logger.info(error)
        messages.error(request, 'Invalid search expression')
        return redirect('archive')
    if data.get('token'):
        response.set_cookie('downloadToken', data.get('token'))
    return response


def legacy_message(request, list_name, id):
    """Redirect to the appropriate message given list name and legacy number"""
    if not id.isdigit():
        raise Http404("Message not found")
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
            os.chmod(settings.LOG_FILE, 0o666)
        except OSError:
            pass

    return render(request, 'archive/main.html', {
        'form': form,
        'lists': get_lists_for_user(request.user),
    })


class MessageDetailView(DetailView):
    model = Message


class ReportsSubscribersView(LoginRequiredMixin, CSVResponseMixin, TemplateView):
    """Subscriber Counts Report"""
    template_name = 'archive/reports_subscribers.html'
    csv_fields = ['email_list.name', 'count']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = dict(self.request.GET.items())
        date = None
        if self.request.GET.get('date'):
            try:
                date = isoparse(self.request.GET.get('date'))
                # convert datetime to date
                date = date.date()
            except ValueError:
                pass
        if not date:
            date = datetime.date.today() - relativedelta(months=1)
            date = date.replace(day=1)
        context['object_list'] = Subscriber.objects.filter(email_list__private=False, date=date)
        context['date'] = date
        export_params = params.copy()
        export_params['export'] = 'csv'
        context['export_query_string'] = urlencode(export_params)
        return context


class ReportsMessagesView(LoginRequiredMixin, CSVResponseMixin, TemplateView):
    """Message Counts Report"""
    template_name = 'archive/reports_messages.html'
    csv_fields = ['listname', 'count']

    def get_message_stats(self, sdate, edate):
        """Returns a tuple ( total messages, message counts as
        list of named tuples (listname, count))"""
        messages = Message.objects.filter(
            date__gte=sdate,
            date__lte=edate,
            email_list__private=False)
        counter = Counter(messages.values_list('email_list__name', flat=True))
        Count = namedtuple('Count', 'listname count')
        data = [Count(i[0], i[1]) for i in counter.items()]
        return (messages.count(), data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = dict(self.request.GET.items())

        form = DateForm(self.request.GET)
        
        # if no date submitted default to last month
        if 'start_date' not in self.request.GET and 'end_date' not in self.request.GET:
            now = datetime.datetime.now(timezone.utc)
            # last day of last month
            edate = now.replace(day=1, hour=23, minute=59, second=0, microsecond=0) - relativedelta(days=1)
            # first day of last month
            sdate = edate.replace(day=1, hour=0, minute=0)
            total, message_counts = self.get_message_stats(sdate, edate)
            form = DateForm(initial={
                'start_date': sdate.strftime('%Y-%m-%d'),
                'end_date': edate.strftime('%Y-%m-%d'),
            })
        elif form.is_valid():
            sdate = form.cleaned_data['start_date']
            edate = form.cleaned_data['end_date']
            total, message_counts = self.get_message_stats(sdate, edate)
            # always pass back an unbound form to avoid annoying is-valid styling
            form = DateForm(initial={
                'start_date': sdate.strftime('%Y-%m-%d'),
                'end_date': edate.strftime('%Y-%m-%d'),
            })
        else:
            sdate = None
            edate = None
            message_counts = []
            total = 0

        export_params = params.copy()
        export_params['export'] = 'csv'
        context['export_query_string'] = urlencode(export_params)
        context['object_list'] = message_counts
        context['total'] = total
        context['sdate'] = sdate
        context['edate'] = edate
        context['form'] = form
        return context


@pad_id
@check_access
def message_download(request, list_name, id, msg):
    """Returns the raw message text
    NOTE: the "msg" argument is a Message object added by the check_access decorator
    """
    content = msg.get_body_raw()
    response = HttpResponse(content, content_type='message/rfc822')
    filename = '{}_{}.eml'.format(msg.email_list.name, msg.msgid[:6])
    response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
    return response
