from celery_haystack.indexes import CelerySearchIndex
from haystack import indexes

from mlarchive.archive.models import Message


class XapianMessageIndex(CelerySearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)

    date = indexes.DateTimeField(model_attr='date')
    email_list = indexes.CharField(model_attr='email_list__name', faceted=True)
    frm = indexes.CharField(model_attr='frm')
    frm_name = indexes.CharField(model_attr='frm_name', faceted=True)
    msgid = indexes.CharField(model_attr='msgid')
    subject = indexes.CharField(model_attr='subject')
    tdate = indexes.DateTimeField(model_attr='thread_date')
    tid = indexes.IntegerField(model_attr='thread_id')
    torder = indexes.IntegerField(model_attr='thread_order')
    to = indexes.CharField(model_attr='to_and_cc')
    spam_score = indexes.IntegerField(model_attr='spam_score')

    def get_model(self):
        return Message

    # def index_queryset(self):
    #    """Used when the entire index for model is updated."""
    #    return Note.objects.filter(pub_date__lte=datetime.datetime.now())

    # this is required in order to use start_date, end_date when reindexing
    def get_updated_field(self):
        return 'updated'


class ElasticMessageIndex(CelerySearchIndex, indexes.Indexable):
    """Define Index fields.

    For Elastidsearch, faceted=True creates the Keyword (unanalyzed) field type.
    """
    text = indexes.CharField(document=True, use_template=True)

    date = indexes.DateTimeField(model_attr='date')
    email_list = indexes.CharField(model_attr='email_list__name', faceted=True, indexed=False)
    # frm = indexes.CharField(model_attr='frm',index_fieldname='from', faceted=True, indexed=False)
    frm = indexes.CharField(model_attr='frm', faceted=True)
    frm_name = indexes.CharField(model_attr='frm_name', faceted=True, indexed=False)
    msgid = indexes.CharField(model_attr='msgid', indexed=False)
    subject = indexes.CharField(model_attr='subject')
    tdate = indexes.DateTimeField(model_attr='thread_date')
    tid = indexes.IntegerField(model_attr='thread_id')
    torder = indexes.IntegerField(model_attr='thread_order')
    to = indexes.CharField(model_attr='to_and_cc')
    spam_score = indexes.IntegerField(model_attr='spam_score')

    def get_model(self):
        return Message

    def get_updated_field(self):
        return 'updated'
