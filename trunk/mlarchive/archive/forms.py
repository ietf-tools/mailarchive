from django import forms
from django.conf import settings
from django.contrib import messages
#from haystack.backends.xapian_backend import SearchBackend   #v1.2.7
from haystack.backends.xapian_backend import XapianSearchBackend
from haystack.forms import SearchForm
from haystack.query import SearchQuerySet
from mlarchive.archive.getSQ import parse
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import get_noauth

from datetime import datetime, timedelta

FIELD_CHOICES = (('text','Subject and Body'),
                 ('subject','Subject'),
                 ('frm','From'),
                 ('to','To'),
                 ('msgid','Message-ID'))
                 
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
class AdvancedSearchForm(SearchForm):
    start_date = forms.DateField(required=False,help_text='YYYY-MM-DD')
    end_date = forms.DateField(required=False)
    email_list = forms.CharField(max_length=255,required=False,widget=forms.HiddenInput)
    subject = forms.CharField(max_length=255,required=False)
    frm = forms.CharField(max_length=255,required=False)
    msgid = forms.CharField(max_length=255,required=False)
    #operator = forms.ChoiceField(choices=(('AND','ALL'),('OR','ANY')))
    so = forms.CharField(max_length=25,required=False,widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(self.__class__, self).__init__(*args, **kwargs)
        
    def search(self):
        '''
        Custom search function.  This completely overrides the parent
        search().
        '''
        # First, store the SearchQuerySet received from other processing.
        #sqs = super(DateRangeSearchForm, self).search()
        
        if not self.is_valid():
            #assert False, self.errors
            return self.no_query_found()
        
        q = self.cleaned_data['q']
    
        #if not self.cleaned_data.get('q'):
        #    return self.no_query_found()

        #sqs = self.searchqueryset.auto_query(self.cleaned_data['q'])
        #backend = XapianSearchBackend('default',PATH=settings.HAYSTACK_XAPIAN_PATH)
        #query = backend.parse_query(self.cleaned_data['q'])
        #sqs = self.searchqueryset.raw_search(query)
        
        # use custom parser
        if q:
            sq = parse(q)
            sqs = self.searchqueryset.filter(sq)
        else:
            sqs = self.searchqueryset

        # handle URL parameters
        if self.cleaned_data['email_list']:
            sqs = sqs.filter(email_list__in=self.cleaned_data['email_list'])
            
        if self.cleaned_data['end_date']:
            sqs = sqs.filter(date__lte=self.cleaned_data['end_date'])
            
        if self.cleaned_data['frm']:
            sqs = sqs.filter(frm__icontains=self.cleaned_data['frm'])
        
        if self.cleaned_data['msgid']:
            sqs = sqs.filter(msgid__icontains=self.cleaned_data['msgid'])
            
        if self.cleaned_data['qdr']:
            sqs = sqs.filter(date_gte=get_qdr_time(self.cleaned_data['qdr']))
        
        if self.cleaned_data['start_date']:
            sqs = sqs.filter(date__gte=self.cleaned_data['start_date'])
        
        if self.cleaned_data['subject']:
            sqs = sqs.filter(subject__icontains=self.cleaned_data['subject'])
        
        # private lists -------------------------------------------
        if self.request.user.is_authenticated():
            # exclude those lists the user is not authorized for
            sqs = sqs.exclude(email_list__in=get_noauth(self.request))
        else:
            # exclude all private lists
            # TODO cache this query, see Low Level Cache API
            private_ids = [ str(x.pk) for x in EmailList.objects.filter(private=True) ]
            sqs = sqs.exclude(email_list__in=private_ids)
            
        # sorting -------------------------------------------------
        so = self.cleaned_data.get('so',None)
        if so in ('date','-date','email_list','-email_list','frm','-frm'):
            sqs = sqs.order_by(so)
        elif so in ('score','-score'):
            # TODO: order_by('score') doesn't work because its strings, but is default ordering
            pass
        else:
            # default to
            # sqs = sqs.order_by('-date')
            pass
            
        if self.load_all:
            sqs = sqs.load_all()
                
        return sqs
    
    def clean_email_list(self):
        # take a comma separated list of email_list names and convert to list of ids
        user = self.request.user
        ids = []
        bad_lists = []
        email_list = self.cleaned_data['email_list']
        for name in self.cleaned_data['email_list'].split(','):
            try:
                ids.append(EmailList.objects.get(name=name).id)
            except EmailList.DoesNotExist:
                bad_lists.append(name)
        
        # TODO
        #if bad_lists:
        #    messages.warning(self.request, 'This feature is disabled')
        
        """
        # don't allow inclusion of unauthorized lists
        # TODO: consider just adding exclude to sqs to restrict lists
        if not user.is_authenticated():
            noauth_ids = [ x.id for x in EmailList.objects.filter(private=True) ]
        else:
            noauth_ids = [ x.id for x in EmailList.objects.filter(private=True).exclude(members=user) ]
        qset = set(ids)
        restricted = set(noauth_ids)
        # subtract restricted email_list ids
        nset = qset.difference(restricted)
        return list(nset)
        """
        return ids
        
    def clean(self):
        super(AdvancedSearchForm, self).clean()
        cleaned_data = self.cleaned_data

        # error if all fields empty
        
        return cleaned_data

# ---------------------------------------------------------

class RulesForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES,widget=forms.Select(attrs={'class':'parameter'}))
    value = forms.CharField(max_length=120,widget=forms.TextInput(attrs={'class':'operand'}))

class SqlSearchForm(forms.Form):
    start = forms.DateField(required=False)
    end = forms.DateField(required=False)
    subject = forms.CharField(max_length=100,required=False)
    body = forms.CharField(max_length=100,required=False)

class BrowseForm(forms.Form):
    list_name = forms.CharField(max_length=100,required=True,label='List')
    