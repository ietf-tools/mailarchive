from django import forms
from django.conf import settings
from django.contrib import messages
from haystack.backends.xapian_backend import XapianSearchBackend
from haystack.forms import SearchForm, FacetedSearchForm
from haystack.query import SearchQuerySet
from mlarchive.archive.query_utils import parse, get_kwargs
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_noauth

import operator

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

FIELD_CHOICES = (('text','Subject and Body'),
                 ('subject','Subject'),
                 ('frm','From'),
                 ('to','To'),
                 ('msgid','Message-ID'))

QUALIFIER_CHOICES = (('contains','contains'),
                     ('exact','exact'))
                     #('startswith','startswith'))

TIME_CHOICES = (('a','anytime'),
                ('d','day'),
                ('w','week'),
                ('m','month'),
                ('y','year'),
                ('c','custom...'))

VALID_SORT_OPTIONS = ('frm','-frm','date','-date','email_list','-email_list', 'subject', '-subject')

# --------------------------------------------------------
# Helper Functions
# --------------------------------------------------------
def sort_by_thread(qs, reverse=False):
    '''Sort the given query by thread'''
    new_query = qs._clone()
    # pass one, create thread-latest_date mapping
    map = {}
    for item in new_query:                          # this causes causes cache to be filled
        val = map.get(item.object.thread.id,None)
        if not val:
            map[item.object.thread.id] = item.date
            continue
        if val < item.date:
            map[item.object.thread.id] = item.date

    # order map by date
    map = sorted(map.iteritems(),key=operator.itemgetter(1))
    order = { x[0]:i for i,x in enumerate(map) }

    # build sorted list of SearchResult objects
    result = sorted(new_query, key=lambda x: (order[x.object.thread.id],x.date),reverse=reverse)

    # swap in sorted list
    new_query._result_cache = result

    return new_query

def transform(val):
    '''
    This function takes a sort parameter and validates and transforms it for use
    in an order_by clause.
    '''
    if val not in VALID_SORT_OPTIONS:
        return ''
    if val in ('frm','-frm'):
        val = val + '_email'    # use just email portion of from
    return val

# --------------------------------------------------------
class AdminForm(forms.Form):
    email_list = forms.ModelChoiceField(EmailList.objects.all(),empty_label='(All lists)',required=False)
    end_date = forms.DateField(required=False)
    frm = forms.CharField(max_length=255,required=False)
    msgid = forms.CharField(max_length=255,required=False)
    spam = forms.BooleanField(required=False)
    start_date = forms.DateField(required=False)
    subject = forms.CharField(max_length=255,required=False)

    def clean_email_list(self):
        # return a list of names even though there's ever only one, so we match get_kwargs() api
        email_list = self.cleaned_data['email_list']
        if email_list:
            return [email_list.name]

class AdvancedSearchForm(FacetedSearchForm):
    start_date = forms.DateField(required=False,widget=forms.TextInput(attrs={'class':'defaultText','title':'YYYY-MM-DD'}))
    end_date = forms.DateField(required=False,widget=forms.TextInput(attrs={'class':'defaultText','title':'YYYY-MM-DD'}))
    email_list = forms.CharField(max_length=255,required=False,widget=forms.HiddenInput)
    subject = forms.CharField(max_length=255,required=False)
    frm = forms.CharField(max_length=255,required=False)
    msgid = forms.CharField(max_length=255,required=False)
    #operator = forms.ChoiceField(choices=(('AND','ALL'),('OR','ANY')))
    so = forms.CharField(max_length=25,required=False,widget=forms.HiddenInput)
    sso = forms.CharField(max_length=25,required=False,widget=forms.HiddenInput)
    # filter fields
    #qdr = forms.CharField(max_length=25,required=False)
    qdr = forms.ChoiceField(choices=TIME_CHOICES,required=False)
    f_list = forms.CharField(max_length=255,required=False)
    f_from = forms.CharField(max_length=255,required=False)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(self.__class__, self).__init__(*args, **kwargs)

    def search(self):
        '''
        Custom search function.  This completely overrides the parent
        search().  Should return a SearchQuerySet object.
        '''
        # for now if search form doesn't validate return empty results
        if not self.is_valid():
            #assert False, self.errors
            # TODO
            # messages.warning(self.request, 'invalid search parameters')
            return self.no_query_found()

        '''
        Original search function.  By using backend directly we could take advantage
        of Xapian's impressive query parsing.  However the resulting QuerySet does
        not support chaining so it's not going to work for us.

        sqs = self.searchqueryset.auto_query(self.cleaned_data['q'])
        backend = XapianSearchBackend('default',PATH=settings.HAYSTACK_XAPIAN_PATH)
        query = backend.parse_query(self.cleaned_data['q'])
        sqs = self.searchqueryset.raw_search(query)
        '''

        # use custom parser-----------------------------------------
        if self.cleaned_data.get('q'):
            query = parse(self.cleaned_data['q'])
            logger.info('Query:%s' % query)
            sqs = self.searchqueryset.filter(query)
        else:
            sqs = self.searchqueryset

        # handle URL parameters ------------------------------------
        kwargs = get_kwargs(self.cleaned_data)

        if kwargs:
            sqs = sqs.filter(**kwargs)

        # filters -------------------------------------------------
        if self.cleaned_data['f_list']:
            f_list = self.cleaned_data['f_list'].split(',')
            sqs = sqs.filter(email_list__in=f_list)
        if self.cleaned_data['f_from']:
            f_from = self.cleaned_data['f_from'].split(',')
            sqs = sqs.filter(frm_email__in=f_from)

        # private lists -------------------------------------------
        if self.request.user.is_authenticated():
            if not self.request.user.is_superuser:
                # exclude those lists the user is not authorized for
                sqs = sqs.exclude(email_list__in=get_noauth(self.request))
        else:
            # exclude all private lists
            # TODO cache this query, see Low Level Cache API
            private_lists = [ str(x.name) for x in EmailList.objects.filter(private=True) ]
            sqs = sqs.exclude(email_list__in=private_lists)

        # Populate all all SearchResult.object with efficient db query
        # when called via urls.py / search_view_factory default load_all=True
        if self.load_all:
            sqs = sqs.load_all()

        # faceting ------------------------------------------------
        # calling sqs.facet() causes query to be rerun, therefore this
        # needs to be run before doing any custom sorts, ie. thread
        sqs = sqs.facet('email_list').facet('frm_email')

        # sorting -------------------------------------------------
        # perform this step last because other operations may cause
        # query to be re-run which loses custom sort order
        so = transform(self.cleaned_data.get('so'))
        sso = transform(self.cleaned_data.get('sso'))

        if so:
            if so == 'thread':
                sqs = sort_by_thread(sqs,reverse=True)
            else:
                sqs = sqs.order_by(so,sso)
        else:
            # if there's no "so" param, and no query we are browsing, sort by -date
            if len(kwargs) == 1 and kwargs.get('email_list__in'):
                sqs = sqs.order_by('-date')

        return sqs

    def clean_email_list(self):
        # take a comma separated list of email_list names and convert to list of names
        email_list = self.cleaned_data['email_list']
        if email_list:
            return email_list.split(',')
        else:
            return None
# ---------------------------------------------------------

class BrowseForm(forms.Form):
    list_name = forms.CharField(max_length=100,required=True,label='List')

class FilterForm(forms.Form):
    time = forms.ChoiceField(choices=TIME_CHOICES)

class RulesForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES,widget=forms.Select(attrs={'class':'parameter'}))
    qualifier = forms.ChoiceField(choices=QUALIFIER_CHOICES,widget=forms.Select(attrs={'class':'qualifier'}))
    value = forms.CharField(max_length=120,widget=forms.TextInput(attrs={'class':'operand'}))

