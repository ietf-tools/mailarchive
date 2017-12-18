from celery_haystack.indexes import CelerySearchIndex
from django.conf import settings
from haystack import indexes

from mlarchive.archive.models import Message

#BaseSearch = indexes.RealTimeSearchIndex if settings.HAYSTACK_USE_REALTIME_SEARCH else indexes.SearchIndex

from mlarchive.utils.test_utils import get_search_backend
if get_search_backend() == 'xapian':
    from mlarchive.archive.indexes import XapianMessageIndex as MessageIndex
else:
    from mlarchive.archive.indexes import ElasticMessageIndex as MessageIndex


