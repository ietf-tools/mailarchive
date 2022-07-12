import logging
import re
import six

from elasticsearch import Elasticsearch, TransportError
from elasticsearch.helpers import bulk
from elasticsearch_dsl import Search, A, Q

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_str

from mlarchive.archive.query_utils import (queries_from_params,
    filters_from_params, get_order_fields, generate_queryid, parse_query)
from mlarchive.archive.utils import get_noauth

logger = logging.getLogger(__name__)
IDENTIFIER_REGEX = re.compile('^[\w\d_]+\.[\w\d_]+\.[\w\d-]+$')


def full_prepare(message):
    '''Takes database Message object and returns dictionary for index update.
    For dates use isoformat().'''
    logger.debug('full_prepare pk:{}'.format(message.pk))
    prepared_data = {
        'id': 'archive.message.' + force_str(message.pk),
        'django_ct': 'archive.message',
        'django_id': force_str(message.pk),
    }
    prepared_data['text'] = '\n'.join([message.subject, message.get_body()])
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


class ESBackend():
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
        'settings': {
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
        if not self.client.indices.exists(self.index_name):
            self.client.indices.create(index=self.index_name,
                                       body=self.DEFAULT_SETTINGS)
            self.client.indices.put_mapping(index=self.index_name,
                                            body=self.mapping)

        self.setup_complete = True

    def clear(self, commit=True):
        '''Clears index of all data, and runs setup, leaving 
        an empty index.'''
        logger.debug('ESBackend.clear() called.')
        self.client.indices.delete(index=self.index_name, ignore=404)
        self.setup()

    def update(self, iterable, commit=True):
        '''Update index records using iterable of instances'''
        logger.debug('ESBackend.update() called. iterable={}, iterable_length={}, last_message={}, commit={}, setup_complete={}'.format(
            type(iterable), len(iterable), iterable[-1].django_id, commit, self.setup_complete))
        
        if not self.setup_complete:
            try:
                self.setup()
            except TransportError as e:
                if not self.silently_fail:
                    raise
                self.log.error("Failed to add documents to Elasticsearch: %s", e, exc_info=True)
                return

        prepped_docs = []
        for obj in iterable:
            try:
                prepped_data = full_prepare(obj)
                # final_data = {}

                # Convert the data to make sure it's happy.
                # - handled already (dates=isoformat, no binary)
                # for key, value in prepped_data.items():
                #     final_data[key] = self._from_python(value)

                # what is this for?
                # final_data['_id'] = final_data['id']
                prepped_data['_id'] = prepped_data['id']

                prepped_docs.append(prepped_data)
            # except SkipDocument:
            #     log.debug(u"Indexing for object `%s` skipped", obj)
            except TransportError as e:
                if not settings.ELASTICSEARCH_SILENTLY_FAIL:
                    raise

                # We'll log the object identifier but won't include the actual object
                # to avoid the possibility of that generating encoding errors while
                # processing the log message:
                extra = {"data": {"index": self.index_name,
                                  "object": force_str(obj.pk)}}
                logger.error(
                    u"%s while preparing object for update" % e.__class__.__name__,
                    exec_info=True,
                    extra=extra)

        results = bulk(self.client, prepped_docs,
                       index=self.index_name)
        logger.debug('ESBackend.update() bulk results={}'.format(results))

        if commit:
            self.client.indices.refresh(index=self.index_name)

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


class ElasticsearchQuery():
    '''Class for creating Elasticsearch Search objects from input forms.

    The input form must have a Request object attached in order to 
    determine access to private lists
    '''

    def __init__(self, form, email_list=None, skip_facets=False):
        self.form = form
        self.request = form.request
        connection_options = settings.ELASTICSEARCH_CONNECTION
        self.client = Elasticsearch(
            connection_options['URL'],
            index=connection_options['INDEX_NAME'],
            **connection_options.get('KWARGS', {}))
        self.search = Search(using=self.client, index=settings.ELASTICSEARCH_INDEX_NAME)
        self.skip_facets = skip_facets
        self.email_list = email_list
        self.queries = []
        self.filters = []

    def add_aggregates(self):
        """Set aggs on search"""
        list_terms = A('terms', field='email_list')
        from_terms = A('terms', field='frm_name')
        self.search.aggs.bucket('list_terms', list_terms)
        self.search.aggs.bucket('from_terms', from_terms)

    def build_search(self):
        '''Build the Search object from form inputs'''

        # if form doesn't validate return empty result set
        if not self.form.is_valid():
            return self.empty_query()

        self.process_queries()
        self.process_filters()
        self.exclude_private_lists()
        if not self.skip_facets:
            self.add_aggregates()
        self.handle_sort()
        self.post_process()

        return self.search

    def empty_query(self):
        search = self.search.query('term', dummy='')
        return search

    def exclude_private_lists(self):
        self.search = self.search.exclude(
            'terms',
            email_list=get_noauth(self.request.user))

    def handle_sort(self):
        fields = get_order_fields(self.request.GET)
        logger.debug('sort fields: {}'.format(fields))
        self.search = self.search.sort(*fields)

    def post_process(self):
        # if no search parameters at all, return empty set
        # logger.debug('elastic search: {}'.format(self.search.to_dict()))
        if not any([self.queries, self.filters]):
            self.search = self.empty_query()
            return

        # save query in cache with random id for security
        queryid = generate_queryid()
        self.search.query_string = self.request.META['QUERY_STRING']
        self.search.queryid = queryid
        logger.debug('Saved queryid to query: {}'.format(queryid))
        # Cache search as dictionary, use s.from_dict() on retrieval
        cache.set(queryid, self.search.to_dict(), 7200)           # 2 hours
        logger.debug('Backend Query: {}'.format(self.search.to_dict()))
        # logger.debug('search.count: {}'.format(self.search.count()))

    def process_queries(self):
        # handle special "q" query
        self.q = parse_query(self.request)
        if self.q:
            logger.info('Query String: %s' % self.q)
            logger.debug('Query Params: %s' % self.request.GET)
            self.queries.append(Q(
                'query_string',
                query=self.q,
                default_field='text',
                default_operator=settings.ELASTICSEARCH_DEFAULT_OPERATOR))

        # handle queries from URL parameters
        self.queries.extend(queries_from_params(self.form.cleaned_data))
        for q in self.queries:
            self.search = self.search.query(q)

    def process_filters(self):
        # TODO: revisit this implementation, used with browse
        if self.email_list:
            self.filters.append(Q('term', email_list=self.email_list.name))
        self.filters.extend(filters_from_params(self.form.cleaned_data))
        for f in self.filters:
            self.search = self.search.filter(f)


def get_identifier(obj_or_string):
    """
    Get an unique identifier for the object or a string representing the
    object.

    If not overridden, uses <app_label>.<object_name>.<pk>.
    """
    if isinstance(obj_or_string, six.string_types):
        if not IDENTIFIER_REGEX.match(obj_or_string):
            raise AttributeError(u"Provided string '%s' is not a valid identifier." % obj_or_string)

        return obj_or_string

    return u"%s.%s" % (get_model_ct(obj_or_string),
                       obj_or_string._get_pk_val())


def get_model_ct_tuple(model):
    # Deferred models should be identified as if they were the underlying model.
    model_name = model._meta.concrete_model._meta.model_name \
        if hasattr(model, '_deferred') and model._deferred else model._meta.model_name
    return (model._meta.app_label, model_name)


def get_model_ct(model):
    return "%s.%s" % get_model_ct_tuple(model)


def search_from_form(form, *args, **kwargs):
    """Create an Elasticsearch Search object from form inputs"""
    return ElasticsearchQuery(form, *args, **kwargs).build_search()
