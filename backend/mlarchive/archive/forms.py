

import hashlib
import six
import time
from collections import OrderedDict

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from haystack.forms import FacetedSearchForm

from mlarchive.archive.query_utils import (get_kwargs, generate_queryid, get_filter_params,
    parse_query, get_base_query, get_order_fields)
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_noauth
from mlarchive.utils.decorators import log_timing

import logging
logger = logging.getLogger(__name__)

FIELD_CHOICES = (('text', 'Subject and Body'),
                 ('subject', 'Subject'),
                 ('from', 'From'),
                 ('to', 'To'),
                 ('msgid', 'Message-ID'))

QUALIFIER_CHOICES = (('contains', 'contains'),
                     ('exact', 'exact'))

TIME_CHOICES = (('a', 'Any time'),
                ('d', 'Past 24 hours'),
                ('w', 'Past week'),
                ('m', 'Past month'),
                ('y', 'Past year'),
                ('c', 'Custom range...'))


# --------------------------------------------------------
# Helper Functions
# --------------------------------------------------------


def get_cache_key(request):
    """Returns a hash key that identifies a unique query.  First we strip all URL
    parameters that do not modify the result set, ie. sort order.  We order the
    parameters for consistency and finally add the request.user because different
    users will have access to different private lists and therefor have different
    results sets.
    """
    base_query = get_base_query(request.GET)
    ordered = OrderedDict(sorted(base_query.items()))
    m = hashlib.md5()
    m.update(urlencode(ordered).encode('utf8'))
    m.update(str(request.user).encode('utf8'))
    return m.hexdigest()


# --------------------------------------------------------
# Fields
# --------------------------------------------------------


def yyyymmdd_to_strftime_format(fmt):
    translation_table = sorted([
        ("yyyy", "%Y"),
        ("yy", "%y"),
        ("mm", "%m"),
        ("m", "%-m"),
        ("MM", "%B"),
        ("M", "%b"),
        ("dd", "%d"),
        ("d", "%-d"),
    ], key=lambda t: len(t[0]), reverse=True)

    res = ""
    remaining = fmt
    while remaining:
        for pattern, replacement in translation_table:
            if remaining.startswith(pattern):
                res += replacement
                remaining = remaining[len(pattern):]
                break
        else:
            res += remaining[0]
            remaining = remaining[1:]
    return res


class DatepickerDateField(forms.DateTimeField):
    """DateField with some glue for triggering JS Bootstrap datepicker."""

    def __init__(self, date_format, picker_settings={}, *args, **kwargs):
        strftime_format = yyyymmdd_to_strftime_format(date_format)
        kwargs["input_formats"] = [strftime_format]
        kwargs["widget"] = forms.DateInput(format=strftime_format)
        super(DatepickerDateField, self).__init__(*args, **kwargs)

        self.widget.attrs["data-provide"] = "datepicker"
        self.widget.attrs["data-date-format"] = date_format
        if "placeholder" not in self.widget.attrs:
            self.widget.attrs["placeholder"] = date_format
        for k, v in list(picker_settings.items()):
            self.widget.attrs["data-date-%s" % k] = v


# --------------------------------------------------------
# Forms
# --------------------------------------------------------


class AdminForm(forms.Form):
    subject = forms.CharField(max_length=255, required=False)
    frm = forms.CharField(max_length=255, required=False)
    msgid = forms.CharField(max_length=255, required=False)
    start_date = DatepickerDateField(
        date_format="yyyy-mm-dd",
        picker_settings={"autoclose": "1"},
        label='Start date',
        required=False)
    end_date = DatepickerDateField(
        date_format="yyyy-mm-dd",
        picker_settings={"autoclose": "1"},
        label='End date',
        required=False)
    email_list = forms.ModelMultipleChoiceField(
        queryset=EmailList.objects.all().order_by('name'),
        to_field_name='name',
        required=False)
    spam = forms.BooleanField(required=False)
    spam_score = forms.CharField(max_length=6, required=False)
    exclude_whitelisted_senders = forms.BooleanField(required=False)

    def clean_email_list(self):
        # return a list of names for use in search query
        # so we match get_kwargs() api
        email_list = self.cleaned_data.get('email_list')
        if email_list:
            return [e.name for e in email_list]


class AdminActionForm(forms.Form):
    action = forms.CharField(max_length=255)


class LowerCaseModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def prepare_value(self, value):
        if not value:
            return []
        if hasattr(value, '__iter__') and isinstance(value[0], six.string_types):
            value = [v.lower() for v in value if isinstance(v, six.string_types)]
        return super(LowerCaseModelMultipleChoiceField, self).prepare_value(value)


# @method_decorator(log_timing, name='get_facets')
class AdvancedSearchForm(FacetedSearchForm):
    # start_date = forms.DateField(required=False,
    #        widget=forms.TextInput(attrs={'class':'defaultText','title':'YYYY-MM-DD'}))
    start_date = DatepickerDateField(
        date_format="yyyy-mm-dd",
        picker_settings={"autoclose": "1"},
        label='Start date',
        required=False)
    # end_date = forms.DateField(required=False,
    #        widget=forms.TextInput(attrs={'class':'defaultText','title':'YYYY-MM-DD'}))
    end_date = DatepickerDateField(
        date_format="yyyy-mm-dd",
        picker_settings={"autoclose": "1"},
        label='End date',
        required=False)
    # email_list = forms.CharField(max_length=255,required=False,widget=forms.HiddenInput)
    email_list = LowerCaseModelMultipleChoiceField(queryset=EmailList.objects, to_field_name='name', required=False)
    subject = forms.CharField(max_length=255, required=False)
    frm = forms.CharField(max_length=255, required=False)
    msgid = forms.CharField(max_length=255, required=False)
    # operator = forms.ChoiceField(choices=(('AND','ALL'),('OR','ANY')))
    so = forms.CharField(max_length=25, required=False, widget=forms.HiddenInput)
    sso = forms.CharField(max_length=25, required=False, widget=forms.HiddenInput)
    spam_score = forms.CharField(max_length=3, required=False)
    # group and filter fields
    gbt = forms.BooleanField(required=False)                     # group by thread
    qdr = forms.ChoiceField(choices=TIME_CHOICES, required=False, label='Time')  # qualified date range
    f_list = forms.CharField(max_length=255, required=False)
    f_from = forms.CharField(max_length=255, required=False)
    to = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        # can't use reserved word "from" as field name, so we need to map to "frm"
        # args is a tuple and args[0] is either None or a QueryDict
        if len(args) and isinstance(args[0], dict) and 'from' in args[0]:
            args = list(args)
            args[0] = args[0].copy()
            args[0].setlist('frm', args[0].pop('from'))

        super(self.__class__, self).__init__(*args, **kwargs)
        self.fields["email_list"].widget.attrs["placeholder"] = "List names"

    def get_facets(self, sqs):
        """Get facets for the SearchQuerySet

        Because we have two optional filters: f_list, f_from, we need to take into
        consideration if a filter has been applied.  The filters need to interact.
        Therefore each filter set is limited by the other filter's results.

        NOTE: this function expects to receive the query that has not yet applied
        filters.
        """
        cache_key = get_cache_key(self.request)
        facets = cache.get(cache_key)
        if facets:
            return facets

        # calculating facet_counts on large results sets is too costly so skip it
        # If you call results.count() before results.facet_counts() the facet_counts
        # are corrupted in Xapian backend.

        temp = sqs._clone()
        count = temp.count()
        facets = {'fields': {}, 'dates': {}, 'queries': {}}

        if 0 < count < settings.FILTER_CUTOFF:
            clone = sqs._clone()
            sqs = clone.facet('email_list').facet('frm_name')

            # if query contains no filters compute simple facet counts
            filters = get_filter_params(self.request.GET)
            if not filters:
                facets = sqs.facet_counts()

            elif filters == ['f_list']:
                base = sqs.facet_counts()
                filtered = sqs.filter(email_list__in=self.f_list).facet_counts()
                base['fields']['frm_name'] = filtered['fields']['frm_name']
                facets = base

            elif filters == ['f_from']:
                base = sqs.facet_counts()
                filtered = sqs.filter(frm_name__in=self.f_from).facet_counts()
                base['fields']['email_list'] = filtered['fields']['email_list']
                facets = base

            # if both f_list and f_from run each filter independently
            else:
                copy = sqs._clone()
                frm_count = sqs.filter(frm_name__in=self.f_from).facet_counts()
                list_count = copy.filter(email_list__in=self.f_list).facet_counts()
                facets['fields']['email_list'] = frm_count['fields']['email_list']
                facets['fields']['frm_name'] = list_count['fields']['frm_name']

            for field in facets['fields']:
                facets['fields'][field].sort()  # sort by name

        # save in cache
        cache.set(cache_key, facets)
        return facets

    def process_query(self):
        if self.q:
            logger.info('Query String: %s' % self.q)
            logger.debug('Query Params: %s' % self.data)
            self.searchqueryset.query.raw_search(self.q)

        return self.searchqueryset

    def search(self, email_list=None):
        """Custom search function.  This completely overrides the parent
        search().  Returns a SearchQuerySet object.
        """
        # for now if search form doesn't validate return empty results
        if not self.is_valid():
            return self.no_query_found()

        self.f_list = self.cleaned_data['f_list']
        self.f_from = self.cleaned_data['f_from']
        self.q = parse_query(self.request)
        data = self.cleaned_data
        if email_list:
            data['email_list'] = [email_list.name]
        self.kwargs = get_kwargs(data)

        # return empty queryset if no parameters passed
        if not (self.q or self.kwargs):
            return self.no_query_found()

        sqs = self.process_query()

        # handle URL parameters -----------------------------------
        if self.kwargs:
            sqs = sqs.filter(**self.kwargs)

        # private lists -------------------------------------------
        sqs = sqs.exclude(email_list__in=get_noauth(self.request.user))

        # faceting ------------------------------------------------
        # call this before running sorts or applying filters to queryset
        facets = self.get_facets(sqs)

        # filters -------------------------------------------------
        if self.f_list:
            sqs = sqs.filter(email_list__in=self.f_list)
        if self.f_from:
            sqs = sqs.filter(frm_name__in=self.f_from)

        # Populate all all SearchResult.object with efficient db query
        # when called via urls.py / search_view_factory default load_all=True
        if self.load_all:
            sqs = sqs.load_all()

        # grouping and sorting  -----------------------------------
        # perform this step last because other operations, if they clone the
        # SearchQuerySet, cause the query to be re-run which loses custom sort order
        fields = get_order_fields(self.request.GET)
        sqs = sqs.order_by(*fields)

        # save query in cache with random id for security
        queryid = generate_queryid()
        sqs.query_string = self.request.META['QUERY_STRING']
        sqs.queryid = queryid
        cache.set(queryid, sqs, 7200)           # 2 hours

        logger.debug('Backend Query: %s' % sqs.query.build_query())

        # insert facets just before returning query, so they don't get overridden
        sqs.myfacets = facets

        return sqs

    def clean_email_list(self):
        return [n.name for n in self.cleaned_data.get('email_list', [])]

    def clean_f_list(self):
        # take a comma separated list of email_list names and convert to list
        names = self.cleaned_data['f_list']
        if names:
            return names.split(',')

    def clean_f_from(self):
        names = self.cleaned_data['f_from']
        if names:
            return names.split(',')

# ---------------------------------------------------------


class BrowseForm(forms.Form):
    list = forms.ModelChoiceField(queryset=EmailList.objects, label='List')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(BrowseForm, self).__init__(*args, **kwargs)
        self.fields['list'].queryset = EmailList.objects.exclude(name__in=get_noauth(self.request.user)).order_by('name')
        self.fields["list"].widget.attrs["placeholder"] = "List name"


class FilterForm(forms.Form):
    time = forms.ChoiceField(choices=TIME_CHOICES)


class RulesForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES,
            widget=forms.Select(attrs={'class': 'parameter'}))
    qualifier = forms.ChoiceField(choices=QUALIFIER_CHOICES,
            widget=forms.Select(attrs={'class': 'qualifier'}))
    value = forms.CharField(max_length=120,
            widget=forms.TextInput(attrs={'class': 'operand'}))
