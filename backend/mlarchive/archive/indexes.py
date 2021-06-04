from __future__ import absolute_import, division, print_function, unicode_literals

from celery_haystack.indexes import CelerySearchIndex
from haystack import indexes

from mlarchive.archive.models import Message


class ElasticMessageIndex(CelerySearchIndex, indexes.Indexable):
    """Define Index fields.

    For Elasticsearch, faceted=True creates the keyword (unanalyzed) [field_name]_exact field.
    """
    text = indexes.CharField(document=True, use_template=True)

    date = indexes.DateTimeField(model_attr='date')
    email_list = indexes.CharField(model_attr='email_list__name', faceted=True)
    # frm = indexes.CharField(model_attr='frm',index_fieldname='from', faceted=True, indexed=False)
    frm = indexes.CharField(model_attr='frm')
    frm_name = indexes.CharField(model_attr='frm_name', faceted=True, indexed=False)
    msgid = indexes.CharField(model_attr='msgid', indexed=False)
    # TODO index only subject base, but keep it searchable
    subject = indexes.CharField(model_attr='subject')
    subject_base = indexes.CharField(model_attr='base_subject')
    thread_date = indexes.DateTimeField(model_attr='thread_date', indexed=False)
    thread_id = indexes.IntegerField(model_attr='thread_id')
    thread_depth = indexes.IntegerField(model_attr='thread_depth', indexed=False)
    thread_order = indexes.IntegerField(model_attr='thread_order', indexed=False)
    spam_score = indexes.IntegerField(model_attr='spam_score')
    url = indexes.CharField(model_attr='get_absolute_url', indexed=False)

    def get_model(self):
        return Message

    def get_updated_field(self):
        return 'updated'
