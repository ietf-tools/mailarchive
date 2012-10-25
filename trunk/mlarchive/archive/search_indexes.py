from django.conf import settings
#from haystack.indexes import *
#from haystack import site
from haystack import indexes
from mlarchive.archive.models import Message

BaseSearch = indexes.RealTimeSearchIndex if settings.HAYSTACK_USE_REALTIME_SEARCH else indexes.SearchIndex

class MessageIndex(BaseSearch, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    subject = indexes.CharField(model_attr='subject')
    date = indexes.DateTimeField(model_attr='date')
    frm = indexes.CharField(model_attr='frm')
    email_list = indexes.IntegerField(model_attr='email_list_id')
    msgid = indexes.CharField(model_attr='msgid')

    def get_model(self):
        return Message

    #def index_queryset(self):
    #    """Used when the entire index for model is updated."""
    #    return Note.objects.filter(pub_date__lte=datetime.datetime.now())

#site.register(Message, MessageIndex)
