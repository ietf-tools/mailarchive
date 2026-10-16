import logging
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_str

from elasticsearch import Elasticsearch, TransportError
from elasticsearch.helpers import bulk

from ..base import BaseSearchBackend

logger = logging.getLogger(__name__)
IDENTIFIER_REGEX = re.compile(r'^[\w\d_]+\.[\w\d_]+\.[\w\d-]+$')


def prep_text(message):
    '''Prepare the "text" field that is used as the default field for
    search queries, ie. no field designator'''
    return '\n'.join([message.frm, message.subject, message.get_body()])


def full_prepare(message):
    '''Takes database Message object and returns dictionary for index update.
    For dates use isoformat().'''
    logger.debug('full_prepare pk:{}'.format(message.pk))
    prepared_data = {
        'id': 'archive.message.' + force_str(message.pk),
        'django_ct': 'archive.message',
        'django_id': force_str(message.pk),
    }
    prepared_data['text'] = prep_text(message)
    prepared_data['date'] = message.date.isoformat()
    prepared_data['email_list'] = message.email_list.name
    prepared_data['email_list_exact'] = message.email_list.name
    prepared_data['frm'] = message.frm
    prepared_data['frm_name'] = message.frm_name
    prepared_data['frm_name_exact'] = message.frm_name
    prepared_data['msgid'] = message.msgid
    prepared_data['subject'] = message.subject
    prepared_data['subject_base'] = message.base_subject
    prepared_data['thread_date'] = message.thread_date
    prepared_data['thread_id'] = message.thread_id
    prepared_data['thread_depth'] = message.thread_depth
    prepared_data['thread_order'] = message.thread_order
    prepared_data['spam_score'] = message.spam_score
    prepared_data['url'] = message.get_absolute_url()

    return prepared_data


def get_model_ct_tuple(model):
    # Deferred models should be identified as if they were the underlying model.
    model_name = model._meta.concrete_model._meta.model_name \
        if hasattr(model, '_deferred') and model._deferred else model._meta.model_name
    return (model._meta.app_label, model_name)


def get_model_ct(model):
    return "%s.%s" % get_model_ct_tuple(model)


def get_identifier(obj_or_string):
    """
    Get an unique identifier for the object or a string representing the
    object.

    If not overridden, uses <app_label>.<object_name>.<pk>.
    """
    if isinstance(obj_or_string, str):
        if not IDENTIFIER_REGEX.match(obj_or_string):
            raise AttributeError(u"Provided string '%s' is not a valid identifier." % obj_or_string)

        return obj_or_string

    return u"%s.%s" % (get_model_ct(obj_or_string),
                       obj_or_string._get_pk_val())


class ElasticSearchBackend(BaseSearchBackend):
    """Elasticsearch Backend"""

    # Characters reserved by Elasticsearch for special use.
    # The '\\' must come first, so as not to overwrite the other slash replacements.
    RESERVED_CHARACTERS = (
        '\\', '+', '-', '&&', '||', '!', '(', ')', '{', '}',
        '[', ']', '^', '"', '~', '*', '?', ':', '/',
    )

    # Settings to add an n-gram & edge n-gram analyzers
    # for use in autocomplete feature
    DEFAULT_SETTINGS = {
        "analysis": {
            "analyzer": {
                "ngram_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["ngram_filter", "lowercase"]
                },
                "edgengram_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["edgengram_filter", "lowercase"]
                }
            },
            "tokenizer": {
                "custom_ngram_tokenizer": {
                    "type": "ngram",
                    "min_gram": 4,
                    "max_gram": 4,
                },
                "custom_edgengram_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 4,
                    "max_gram": 4,
                    "side": "front"
                }
            },
            "filter": {
                "ngram_filter": {
                    "type": "ngram",
                    "min_gram": 4,
                    "max_gram": 4
                },
                "edgengram_filter": {
                    "type": "edge_ngram",
                    "min_gram": 4,
                    "max_gram": 4
                }
            }
        }
    }

    def __init__(self):
        connection_options = settings.ELASTICSEARCH_CONNECTION
        if 'URL' not in connection_options:
            raise ImproperlyConfigured("You must specify a 'URL' in your settings for connection Elasticsearch.")

        if 'INDEX_NAME' not in connection_options:
            raise ImproperlyConfigured("You must specify a 'INDEX_NAME' in your settings for connection Elasticsearch.")

        self.client = Elasticsearch(
            connection_options['URL'],
            index=connection_options['INDEX_NAME'],
            http_auth=connection_options['http_auth'],
            **connection_options.get('KWARGS', {}))
        self.index_name = connection_options['INDEX_NAME']
        self.log = logging.getLogger(__name__)
        self.mapping = settings.ELASTICSEARCH_INDEX_MAPPINGS
        self.setup_complete = False
        self.silently_fail = connection_options.get('SILENTLY_FAIL', True)

    def setup(self):
        """
        If the index doesn't exist, create it and set mappings. You can't
        change mappings of existing indexes.
        """
        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(index=self.index_name,
                                       settings=self.DEFAULT_SETTINGS)
            self.client.indices.put_mapping(index=self.index_name,
                                            body=self.mapping)

        self.setup_complete = True

    def clear(self, commit=True):
        '''Clears index of all data, and runs setup, leaving
        an empty index.'''
        logger.debug('ESBackend.clear() called.')
        self.client.indices.delete(index=self.index_name, ignore=404)
        self.setup()

    def update(self, document, commit=True):
        '''Index a single prepared document (dict). For bulk indexing use bulk_update().'''
        if not self.setup_complete:
            try:
                self.setup()
            except TransportError as e:
                if not self.silently_fail:
                    raise
                self.log.error("Failed to add document to Elasticsearch: %s", e, exc_info=True)
                return

        doc_id = document['id']
        self.client.index(index=self.index_name, id=doc_id, body=document)

        if commit:
            self.client.indices.refresh(index=self.index_name)

    def bulk_update(self, documents, commit=True):
        '''Index an iterable of prepared documents (dicts) using the bulk helper.'''
        if not self.setup_complete:
            try:
                self.setup()
            except TransportError as e:
                if not self.silently_fail:
                    raise
                self.log.error("Failed to add documents to Elasticsearch: %s", e, exc_info=True)
                return

        prepped_docs = []
        for doc in documents:
            prepped = dict(doc)
            prepped['_id'] = prepped['id']
            prepped_docs.append(prepped)

        results = bulk(self.client, prepped_docs, index=self.index_name)
        logger.debug('ESBackend.bulk_update() results={}'.format(results))

        if commit:
            self.client.indices.refresh(index=self.index_name)

    def search(self, query, limit=10, **kwargs):
        """Search the index using Elasticsearch simple_query_string syntax.

        Returns the list of hits (each a dict with '_source', '_id', etc.).
        Extra kwargs are merged into the search request body.
        """
        if not self.setup_complete:
            self.setup()
        body = {
            'query': {'simple_query_string': {'query': query}},
            'size': limit,
        }
        body.update(kwargs)
        response = self.client.search(index=self.index_name, body=body)
        return response['hits']['hits']

    def remove(self, obj_or_string, commit=True):
        """Remove record from index"""
        doc_id = get_identifier(obj_or_string)

        if not self.setup_complete:
            try:
                self.setup()
            except TransportError as e:
                if not self.silently_fail:
                    raise

                self.log.error("Failed to remove document '%s' from Elasticsearch: %s", doc_id, e,
                               exc_info=True)
                return

        try:
            self.client.delete(index=self.index_name, id=doc_id, ignore=404)

            if commit:
                self.client.indices.refresh(index=self.index_name)
        except TransportError as e:
            if not self.silently_fail:
                raise

            self.log.error("Failed to remove document '%s' from Elasticsearch: %s", doc_id, e, exc_info=True)
