import logging
import re
import six

from elasticsearch import Elasticsearch, TransportError
from elasticsearch.helpers import bulk

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_text

logger = logging.getLogger(__name__)
IDENTIFIER_REGEX = re.compile('^[\w\d_]+\.[\w\d_]+\.[\w\d-]+$')


def full_prepare(message):
    '''Takes database Message object and returns dictionary for index update.
    For dates use isoformat().'''
    prepared_data = {
        'id': 'archive.message.' + force_text(message.pk),
        'django_ct': 'archive.message',
        'django_id': force_text(message.pk),
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
       
    # Settings to add an n-gram & edge n-gram analyzer.
    DEFAULT_SETTINGS = {
        'settings': {
            "analysis": {
                "analyzer": {
                    "ngram_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["haystack_ngram", "lowercase"]
                    },
                    "edgengram_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["haystack_edgengram", "lowercase"]
                    }
                },
                "tokenizer": {
                    "haystack_ngram_tokenizer": {
                        "type": "nGram",
                        "min_gram": 4,
                        "max_gram": 4,
                    },
                    "haystack_edgengram_tokenizer": {
                        "type": "edgeNGram",
                        "min_gram": 4,
                        "max_gram": 4,
                        "side": "front"
                    }
                },
                "filter": {
                    "haystack_ngram": {
                        "type": "nGram",
                        "min_gram": 4,
                        "max_gram": 4
                    },
                    "haystack_edgengram": {
                        "type": "edgeNGram",
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
            **connection_options.get('KWARGS', {}))
        self.index_name = connection_options['INDEX_NAME']
        self.log = logging.getLogger(__name__)
        self.mapping = settings.ELASTICSEARCH_INDEX_MAPPINGS_NEW
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
                                            doc_type='modelresult',
                                            body=self.mapping)

        self.setup_complete = True

    def clear(self, commit=True):
        '''Clears index of all data'''
        self.client.indices.delete(index=self.index_name, ignore=404)
        # client.indices.create(index=index_name, body=DEFAULT_SETTINGS, ignore=400)
        # ignore 400 cause by IndexAlreadyExistsException when creating an index
        
        self.setup_complete = False

        self.client.indices.create(index=self.index_name, ignore=400)
        self.client.indices.put_mapping(
            index=self.index_name,
            doc_type='modelresult',
            body=self.mapping)

    def update(self, iterable, commit=True):
        '''Update index records using iterable of instances'''
        logger.debug('ESBackend.update() called. iterable={}, commit={}, setup_complete={}'.format(
            type(iterable), commit, self.setup_complete))
        
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
                                  "object": force_text(obj.pk)}}
                logger.error(
                    u"%s while preparing object for update" % e.__class__.__name__,
                    exec_info=True,
                    extra=extra)

        results = bulk(self.client, prepped_docs,
                       index=self.index_name,
                       doc_type='modelresult')
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
            self.client.delete(index=self.index_name, doc_type='modelresult', id=doc_id, ignore=404)

            if commit:
                self.client.indices.refresh(index=self.index_name)
        except TransportError as e:
            if not self.silently_fail:
                raise

            self.log.error("Failed to remove document '%s' from Elasticsearch: %s", doc_id, e, exc_info=True)


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
