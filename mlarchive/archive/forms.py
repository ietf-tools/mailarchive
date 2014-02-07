from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from haystack.backends.xapian_backend import XapianSearchBackend
from haystack.forms import SearchForm, FacetedSearchForm
from haystack.query import SearchQuerySet
from mlarchive.archive.query_utils import parse, get_kwargs
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_noauth

import operator
import random
import xapian

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

FIELD_CHOICES = (('text','Subject and Body'),
                 ('subject','Subject'),
                 ('frm','From'),
                 ('to','To'),
                 ('msgid','Message-ID'))

FILTER_SET = set(['f_list','f_from'])

QUALIFIER_CHOICES = (('contains','contains'),
                     ('exact','exact'))
                     #('startswith','startswith'))

TIME_CHOICES = (('a','anytime'),
                ('d','day'),
                ('w','week'),
                ('m','month'),
                ('y','year'),
                ('c','custom...'))

VALID_SORT_OPTIONS = ('frm','-frm','date','-date','email_list','-email_list',
                      'subject','-subject')

EXTRA_PARAMS = ('so', 'sso', 'page', 'gbt')
ALL_PARAMS = ('f_list','f_from', 'so', 'sso', 'page', 'gbt')

# --------------------------------------------------------
# Helper Functions
# --------------------------------------------------------
def get_base_query(querydict,filters=False,string=False):
    """Get the base query by stripping any extra parameters from the query.
    Expects a QueryDict object, ie. request.GET.  Returns a copy of the querydict
    with parameters removed, or the query as a string if string=True.  Optional boolean
    "filters".  If filters=True leave filter parameters intact. For use with calculating
    base facets.

    NOTE: the base query string we are using as a key is urlencoded.  Another option is to save
    the query unquoted using urlib.unquote_plus()
    """
    if filters:
        params = EXTRA_PARAMS
    else:
        params = ALL_PARAMS
    copy = querydict.copy()
    for key in querydict:
        if key in params:
            copy.pop(key)
    if string:
        return copy.urlencode()
    else:
        return copy

def get_list_info(value):
    """Map list name to list id or list id to list name.  This is essentially a cached
    bi-directional dictionary lookup."""
    mapping = cache.get('list_info')
    if mapping is None:
        mapping = { x.id:x.name for x in EmailList.objects.all() }
        reversed = { v:k for k,v in mapping.items() }
        mapping.update(reversed)
        cache.set('list_info',mapping,86400)
    return mapping.get(value)

def group_by_thread(qs, so, sso, reverse=False):
    """Group query by thread.  Takes a SearchQuerySet, search order (string),
    secondary search order (string), reverse (boolean) and returns a SearchQuerySet
    grouped by message thread"""
    new_query = qs._clone()
    # pass one, create thread-latest_date mapping
    map = {}
    for item in new_query:                      # this causes causes cache to be filled
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

def sort_by_subject(qs, sso, reverse=False):
    new_query = qs._clone()

    # build sorted list of SearchResult objects
    result = sorted(new_query, key=lambda x: x.object.base_subject,reverse=reverse)

    # swap in sorted list
    new_query._result_cache = result

    return new_query

def transform(val):
    """This function takes a sort parameter and validates and transforms it for use
    in an order_by clause.
    """
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
    spam_score = forms.CharField(max_length=3,required=False)
    # group and filter fields
    gbt = forms.BooleanField(required=False)                     # group by thread
    qdr = forms.ChoiceField(choices=TIME_CHOICES,required=False) # qualified date range
    f_list = forms.CharField(max_length=255,required=False)
    f_from = forms.CharField(max_length=255,required=False)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(self.__class__, self).__init__(*args, **kwargs)

    def get_facets(self, sqs):
        """Get facets for the SearchQuerySet

        Because we have two optional filters: f_list, f_from, we need to take into
        consideration if a filter has been applied.  The filters need to interact.
        Therefore each filter set is limited by the other filter's results.

        NOTE: this function expects to receive the query that has not yet applied
        filters.
        """
        # first check the cache
        # leave filter options in facet cache key because counts will be unqiue
        query = get_base_query(self.request.GET,filters=True,string=True)
        facets = cache.get(query)
        if facets:
            return facets

        # calculating facet_counts on large results sets is too costly so skip it
        # If you call results.count() before results.facet_counts() the facet_counts
        # are corrupted.  The solution is to clone the query and call counts on that
        # TODO: this might also be implemented as a timeout
        temp = sqs._clone()
        count = temp.count()

        if 0 < count < settings.FILTER_CUTOFF:
            clone = sqs._clone()
            sqs = clone.facet('email_list').facet('frm_email')

            # if query contains no filters compute simple facet counts
            filters = self.get_filter_params(self.request.GET)
            if not filters:
                facets = sqs.facet_counts()

            # if f_list run base and filtered
            elif filters == ['f_list']:
                base = sqs.facet_counts()
                filtered = sqs.filter(email_list__in=self.f_list).facet_counts()
                # swap out frm_email counts
                base['fields']['frm_email'] = filtered['fields']['frm_email']
                facets = base

            # if f_from run base and filtered
            elif filters == ['f_from']:
                base = sqs.facet_counts()
                filtered = sqs.filter(frm_email__in=self.f_from).facet_counts()
                # swap out email_list counts
                base['fields']['email_list'] = filtered['fields']['email_list']
                facets = base

            # if both f_list and f_from run each filter independently
            else:
                copy = sqs._clone()
                frm_count = sqs.filter(frm_email__in=self.f_from).facet_counts()
                list_count = copy.filter(email_list__in=self.f_list).facet_counts()
                facets = {'fields': {},'dates': {},'queries': {}}
                facets['fields']['email_list'] = frm_count['fields']['email_list']
                facets['fields']['frm_email'] = list_count['fields']['frm_email']

            # map email_list id to name for use in template
            if facets['fields']['email_list']:
                new = [ (get_list_info(x),y) for x,y in facets['fields']['email_list'] ]
                facets['fields']['email_list'] = new

            # sort facets by name
            for field in facets['fields']:
                facets['fields'][field].sort()  # sort by name

        else:
            facets = facets = {'fields': {},'dates': {},'queries': {}}

        # save in cache
        cache.set(query,facets)
        return facets

    def get_filter_params(self, query):
        '''Get filter parameters that appear in the QueryDict'''
        return list(FILTER_SET & set(query.keys()))

    # use custom parser-----------------------------------------
    '''
    def process_query(self):
        if self.q:
            query = parse(self.q)
            logger.info('Query:%s' % query)
            sqs = self.searchqueryset.filter(query)
        else:
            sqs = self.searchqueryset
        return sqs
    '''
    def process_query(self):
        'Use Xapians builtin query parser'
        if self.q:
            #qp = xapian.QueryParser()
            #qp.set_default_op(xapian.Query.OP_AND)
            #qp.add_prefix('from','XFRM')
            #query = qp.parse_query(self.q)
            logger.info('Query:%s' % self.q)
            self.searchqueryset.query.raw_search(self.q)
        return self.searchqueryset

    def search(self):
        """Custom search function.  This completely overrides the parent
        search().  Should return a SearchQuerySet object.
        """
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
        self.f_list = self.cleaned_data['f_list']
        self.f_from = self.cleaned_data['f_from']
        self.q = self.cleaned_data.get('q')

        sqs = self.process_query()

        # handle URL parameters ------------------------------------
        kwargs = get_kwargs(self.cleaned_data)
        if kwargs:
            sqs = sqs.filter(**kwargs)

        # private lists -------------------------------------------
        if self.request.user.is_authenticated():
            if not self.request.user.is_superuser:
                # exclude those lists the user is not authorized for
                sqs = sqs.exclude(email_list__in=get_noauth(self.request))
        else:
            # exclude all private lists
            # TODO cache this query, see Low Level Cache API
            private_lists = [ str(x.id) for x in EmailList.objects.filter(private=True) ]
            #assert False, (private_lists, sqs.count())
            sqs = sqs.exclude(email_list__in=private_lists)

        # faceting ------------------------------------------------
        # call this before running sorts or applying filters to queryset
        facets = self.get_facets(sqs)

        # filters -------------------------------------------------
        if self.f_list:
            sqs = sqs.filter(email_list__in=self.f_list)
        if self.f_from:
            sqs = sqs.filter(frm_email__in=self.f_from)

        # Populate all all SearchResult.object with efficient db query
        # when called via urls.py / search_view_factory default load_all=True
        if self.load_all:
            sqs = sqs.load_all()

        # grouping and sorting  -----------------------------------
        # perform this step last because other operations may cause
        # query to be re-run which loses custom sort order
        so = transform(self.cleaned_data.get('so'))
        sso = transform(self.cleaned_data.get('sso'))
        gbt = self.cleaned_data.get('gbt')

        if gbt:
            sqs = group_by_thread(sqs,so,sso,reverse=True)
        elif so:
            if so == 'subject':
                sqs = sort_by_subject(sqs,sso)
            elif so == '-subject':
                sqs = sort_by_subject(sqs,sso,reverse=True)
            else:
                sqs = sqs.order_by(so,sso)
        else:
            # if there's no "so" param, and no query we are browsing, sort by -date
            if len(kwargs) == 1 and kwargs.get('email_list__in'):
                sqs = sqs.order_by('-date')

        # insert facets just before returning query, so they don't get overridden
        # sqs.query.run()                     # force run of query
        sqs.myfacets = facets

        # save query in cache with random id for security
        queryid = '%032x' % random.getrandbits(128)
        cache.set(queryid,sqs,7200)           # 2 hours
        sqs.queryid = queryid

        return sqs

    def clean_email_list(self):
        # take a comma separated list of email_list names and convert to list of ids
        names = self.cleaned_data['email_list']
        if not names:
            return None
        return map(get_list_info,names.split(','))

    def clean_f_list(self):
        # take a comma separated list of email_list names and convert to list of ids
        names = self.cleaned_data['f_list']
        if not names:
            return None
        return map(get_list_info,names.split(','))

    def clean_f_from(self):
        names = self.cleaned_data['f_from']
        if not names:
            return None
        return names.split(',')

# ---------------------------------------------------------

class BrowseForm(forms.Form):
    list_name = forms.CharField(max_length=100,required=True,label='List')

class FilterForm(forms.Form):
    time = forms.ChoiceField(choices=TIME_CHOICES)

class RulesForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES,widget=forms.Select(attrs={'class':'parameter'}))
    qualifier = forms.ChoiceField(choices=QUALIFIER_CHOICES,widget=forms.Select(attrs={'class':'qualifier'}))
    value = forms.CharField(max_length=120,widget=forms.TextInput(attrs={'class':'operand'}))

