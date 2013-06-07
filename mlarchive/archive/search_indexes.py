from django.conf import settings
#from haystack.indexes import *
#from haystack import site
from haystack import indexes
from mlarchive.archive.models import Message

BaseSearch = indexes.RealTimeSearchIndex if settings.HAYSTACK_USE_REALTIME_SEARCH else indexes.SearchIndex

class MessageIndex(BaseSearch, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    
    date = indexes.DateTimeField(model_attr='date')
    email_list = indexes.CharField(model_attr='email_list__name', faceted=True)
    frm = indexes.CharField(model_attr='frm')
    frm_email = indexes.CharField(model_attr='frm_email', faceted=True)
    msgid = indexes.CharField(model_attr='msgid')
    subject = indexes.CharField(model_attr='subject')
    to = indexes.CharField(model_attr='to')
    spam_score = indexes.IntegerField(model_attr='spam_score')
    
    def get_model(self):
        return Message
    
    #def index_queryset(self):
    #    """Used when the entire index for model is updated."""
    #    return Note.objects.filter(pub_date__lte=datetime.datetime.now())
    
    # this is required in order to use start_date, end_date when reindexing
    def get_updated_field(self):
        return 'updated'
    
#site.register(Message, MessageIndex)
