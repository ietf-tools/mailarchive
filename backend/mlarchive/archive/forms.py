import hashlib
import six
from collections import OrderedDict

from django import forms
from django.utils.http import urlencode

from mlarchive.archive.query_utils import get_base_query
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_noauth


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
class AdvancedSearchForm(forms.Form):
    """The form which builds the elasticsearch-dsl Search object"""
    q = forms.CharField(required=False, label=('Search'),
                        widget=forms.TextInput(attrs={'type': 'search'}))
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
    email_list = LowerCaseModelMultipleChoiceField(queryset=EmailList.objects, to_field_name='name', required=False)
    subject = forms.CharField(max_length=255, required=False)
    frm = forms.CharField(max_length=255, required=False)
    msgid = forms.CharField(max_length=255, required=False)
    # operator = forms.ChoiceField(choices=(('AND','ALL'),('OR','ANY')))
    so = forms.CharField(max_length=25, required=False, widget=forms.HiddenInput)
    sso = forms.CharField(max_length=25, required=False, widget=forms.HiddenInput)
    spam_score = forms.IntegerField(required=False)
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


class SearchForm(forms.Form):
    q = forms.CharField(required=False, label='Search',
                        widget=forms.TextInput(attrs={'type': 'search'}))


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
