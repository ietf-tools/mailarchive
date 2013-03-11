from django import forms
from django.conf import settings
from django.contrib import messages
#from haystack.backends.xapian_backend import SearchBackend   #v1.2.7
from haystack.backends.xapian_backend import XapianSearchBackend
from haystack.forms import SearchForm, FacetedSearchForm
from haystack.query import SearchQuerySet
from mlarchive.archive.getSQ import parse
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_noauth

from datetime import datetime, timedelta

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

FIELD_CHOICES = (('text','Subject and Body'),
                 ('subject','Subject'),
                 ('frm','From'),
                 ('to','To'),
                 ('msgid','Message-ID'))
                 
QUALIFIER_CHOICES = (('contains','contains'),
                     ('exact','exact'),
                     ('startswith','startswith'))
                     
TIME_CHOICES = (('a','anytime'),
                ('d','day'),
                ('w','week'),
                ('m','month'),
                ('y','year'))
# --------------------------------------------------------
# Helper Functions
# --------------------------------------------------------
def get_qdr_time(val):
    '''
    This function expects the value of the qdr search parameter [h,d,w,m,y]
    and returns the corresponding datetime to use in the search filter.
    EXAMPLE: h -> now - one hour
    '''
    now = datetime.now()
    if val == 'h':
        return now - timedelta(hours=1)
    elif val == 'd':
        return now - timedelta(days=1)
    elif val == 'w':
        return now - timedelta(weeks=1)
    elif val == 'm':
        return now - timedelta(days=30)
    elif val == 'y':
        return now - timedelta(days=365)
    

# --------------------------------------------------------
class AdvancedSearchForm(FacetedSearchForm):
    start_date = forms.DateField(required=False,help_text='YYYY-MM-DD')
    end_date = forms.DateField(required=False)
    email_list = forms.CharField(max_length=255,required=False,widget=forms.HiddenInput)
    subject = forms.CharField(max_length=255,required=False)
    frm = forms.CharField(max_length=255,required=False)
    msgid = forms.CharField(max_length=255,required=False)
    #operator = forms.ChoiceField(choices=(('AND','ALL'),('OR','ANY')))
    so = forms.CharField(max_length=25,required=False,widget=forms.HiddenInput)
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
        search().
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
        
        #assert False, self.cleaned_data
        # handle URL parameters ------------------------------------
        kwargs = {}
        if self.cleaned_data['email_list']:
            kwargs['email_list__in'] = self.cleaned_data['email_list']
            
        if self.cleaned_data['end_date']:
            kwargs['date__lte'] = self.cleaned_data['end_date']
            
        frm = self.cleaned_data['frm']
        if frm:
            if frm.find('@')!=-1:
                kwargs['frm_email'] = frm
            else:
                kwargs['frm__icontains'] = frm
        
        if self.cleaned_data['msgid']:
            kwargs['msgid'] = self.cleaned_data['msgid']
            
        if self.cleaned_data['qdr']:
            kwargs['date__gte'] = get_qdr_time(self.cleaned_data['qdr'])
        
        if self.cleaned_data['start_date']:
            kwargs['date__gte'] = self.cleaned_data['start_date']
        
        if self.cleaned_data['subject']:
            kwargs['subject__icontains'] = self.cleaned_data['subject']
            
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
            
        # sorting -------------------------------------------------
        so = self.cleaned_data.get('so')
        if so in ('frm','-frm'):
            sqs = sqs.order_by(so + '_email')   # just email portion of from
        elif so in ('date','-date','email_list','-email_list'):
            sqs = sqs.order_by(so)
        elif so in ('score','-score'):
            # TODO: order_by('score') doesn't work because its strings, but is default ordering
            pass
        else:
            # if there's no "so" param, and no query we are browsing, sort by -date
            sqs = sqs.order_by('-date')
            
        # faceting ------------------------------------------------
        sqs = sqs.facet('email_list').facet('frm_email')
        
        # TODO: do we need this?
        if self.load_all:
            sqs = sqs.load_all()
        
        return sqs
    
    def clean_email_list(self):
        # take a comma separated list of email_list names and convert to list of names
        email_list = self.cleaned_data['email_list']
        if email_list:
            return email_list.split(',')
        else:
            return None
# ---------------------------------------------------------

class RulesForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES,widget=forms.Select(attrs={'class':'parameter'}))
    qualifier = forms.ChoiceField(choices=QUALIFIER_CHOICES)
    value = forms.CharField(max_length=120,widget=forms.TextInput(attrs={'class':'operand'}))

class FilterForm(forms.Form):
    time = forms.ChoiceField(choices=TIME_CHOICES)

class SqlSearchForm(forms.Form):
    start = forms.DateField(required=False)
    end = forms.DateField(required=False)
    subject = forms.CharField(max_length=100,required=False)
    body = forms.CharField(max_length=100,required=False)

class BrowseForm(forms.Form):
    list_name = forms.CharField(max_length=100,required=True,label='List')
    