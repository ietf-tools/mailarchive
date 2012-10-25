from django.conf import settings
from django import forms
#from haystack.backends.xapian_backend import SearchBackend   #v1.2.7
from haystack.backends.xapian_backend import XapianSearchBackend
from haystack.forms import SearchForm
from haystack.query import SearchQuerySet
from mlarchive.archive.models import EmailList
from mlarchive.archive.getSQ import parse

FIELD_CHOICES = (('text','Subject and Body'),
                 ('subject','Subject'),
                 ('frm','From'),
                 ('msgid','Message-id'))
                 
# --------------------------------------------------------
class AdvancedSearchForm(SearchForm):
    start_date = forms.DateField(required=False,help_text='YYYY-MM-DD')
    end_date = forms.DateField(required=False)
    email_list = forms.CharField(max_length=255,required=False)
    subject = forms.CharField(max_length=255,required=False)
    frm = forms.CharField(max_length=255,required=False)
    msgid = forms.CharField(max_length=255,required=False)
    so = forms.CharField(max_length=25,required=False,widget=forms.HiddenInput)

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
            #assert False, sq
            sqs = self.searchqueryset.filter(sq)
        else:
            sqs = self.searchqueryset

        if self.cleaned_data['start_date']:
            sqs = sqs.filter(date__gte=self.cleaned_data['start_date'])

        if self.cleaned_data['end_date']:
            sqs = sqs.filter(date__lte=self.cleaned_data['end_date'])
            
        if self.cleaned_data['email_list']:
            sqs = sqs.filter(email_list__in=self.cleaned_data['email_list'])
        
        if self.cleaned_data['subject']:
            sqs = sqs.filter(subject__icontains=self.cleaned_data['subject'])
            
        if self.cleaned_data['frm']:
            sqs = sqs.filter(frm__icontains=self.cleaned_data['frm'])
        
        if self.cleaned_data['msgid']:
            sqs = sqs.filter(msgid__icontains=self.cleaned_data['msgid'])
        
        # handle sort order if specified
        so = self.cleaned_data.get('so',None)
        if so and so in ('date','email_list','frm','score'):
            sqs = sqs.order_by(so)
            
        if self.load_all:
            sqs = sqs.load_all()
                
        return sqs
    
    def clean_email_list(self):
        # take a comma separated list of email_list names and convert to list of ids
        ids = []
        email_list = self.cleaned_data['email_list']
        if email_list:
            for name in self.cleaned_data['email_list'].split(','):
                ids.append(EmailList.objects.get(name=name).id)
        return ids

    def clean(self):
        super(AdvancedSearchForm, self).clean()
        cleaned_data = self.cleaned_data

        # error if all fields empty
        
        return cleaned_data

class AdvancedSearchForm2(SearchForm):
    operator = forms.ChoiceField(choices=(('AND','ALL'),('OR','ANY')))

# ---------------------------------------------------------

class RulesForm(forms.Form):
    field = forms.ChoiceField(choices=FIELD_CHOICES,widget=forms.Select(attrs={'class':'parameter'}))
    value = forms.CharField(max_length=40,widget=forms.TextInput(attrs={'class':'operand'}))

class SqlSearchForm(forms.Form):
    start = forms.DateField(required=False)
    end = forms.DateField(required=False)
    subject = forms.CharField(max_length=100,required=False)
    body = forms.CharField(max_length=100,required=False)

class BrowseForm(forms.Form):
    list_name = forms.CharField(max_length=100,required=True,label='List')
    