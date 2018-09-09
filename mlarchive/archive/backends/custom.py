from __future__ import absolute_import, division, print_function, unicode_literals

from haystack.inputs import Clean, Exact, PythonData, Raw
from haystack.constants import DEFAULT_OPERATOR, DJANGO_CT, DJANGO_ID, ID
from mlarchive.archive.backends.elasticsearch6 import (Elasticsearch6SearchBackend,
    Elasticsearch6SearchQuery, Elasticsearch6SearchEngine)

from django.conf import settings
from django.utils import six

import logging
logger = logging.getLogger(__name__)


class ConfigurableElasticsearchBackend(Elasticsearch6SearchBackend):
    '''
    A custom ES backend that uses fixed field mappings from settings
    instead of generating them.
    '''

    def build_schema(self, fields):
        content_field_name = 'text'
        mapping = settings.ELASTICSEARCH_INDEX_MAPPINGS
        return (content_field_name, mapping)

    '''
    def build_schema(self, fields):
        content_field_name = ''
        mapping = {
            DJANGO_CT: {'type': 'keyword'},
            DJANGO_ID: {'type': 'long'},
        }

        for field_name, field_class in fields.items():
            field_mapping = FIELD_MAPPINGS.get(field_class.field_type, DEFAULT_FIELD_MAPPING).copy()
            if field_class.boost != 1.0:
                field_mapping['boost'] = field_class.boost

            if field_class.document is True:
                content_field_name = field_class.index_fieldname

            # Do this last to override `text` fields.
            if field_mapping['type'] == 'text':
                if field_class.indexed is False or hasattr(field_class, 'facet_for'):
                    field_mapping['type'] = 'keyword'
                    # field_mapping['index'] = False
                    if 'analyzer' in field_mapping:
                        del field_mapping['analyzer']

            mapping[field_class.index_fieldname] = field_mapping

        return (content_field_name, mapping)
    '''


DEFAULT_FIELD_MAPPING = {'type': 'text'}
FIELD_MAPPINGS = {
    'edge_ngram': {'type': 'text', 'analyzer': 'edgengram_analyzer'},
    'ngram':      {'type': 'text', 'analyzer': 'ngram_analyzer'},
    'date':       {'type': 'date'},
    'datetime':   {'type': 'date'},
    'string':     {'type': 'text'},
    'location':   {'type': 'geo_point'},
    'boolean':    {'type': 'boolean'},
    'float':      {'type': 'float'},
    'long':       {'type': 'long'},
    'integer':    {'type': 'long'},
}


class CustomElasticsearchQuery(Elasticsearch6SearchQuery):
    def build_query_fragment(self, field, filter_type, value):
        """Custom version which excludes wildcards from 'contains' filter_type"""
        from haystack import connections
        query_frag = ''

        if not hasattr(value, 'input_type_name'):
            # Handle when we've got a ``ValuesListQuerySet``...
            if hasattr(value, 'values_list'):
                value = list(value)

            if isinstance(value, six.string_types):
                # It's not an ``InputType``. Assume ``Clean``.
                value = Clean(value)
            else:
                value = PythonData(value)

        # Prepare the query using the InputType.
        prepared_value = value.prepare(self)

        if not isinstance(prepared_value, (set, list, tuple)):
            # Then convert whatever we get back to what pysolr wants if needed.
            prepared_value = self.backend._from_python(prepared_value)

        # 'content' is a special reserved word, much like 'pk' in
        # Django's ORM layer. It indicates 'no special field'.
        if field == 'content':
            index_fieldname = ''
        else:
            index_fieldname = '%s:' % connections[self._using].get_unified_index().get_index_fieldname(field)

        filter_types = {
            'content': '%s',
            # 'contains': u'*%s*',
            'contains': '%s',
            'endswith': '*%s',
            'startswith': '%s*',
            'exact': '%s',
            'gt': '{%s TO *}',
            'gte': '[%s TO *]',
            'lt': '{* TO %s}',
            'lte': '[* TO %s]',
            'fuzzy': '%s~',
        }

        if value.post_process is False:
            query_frag = prepared_value
        else:
            if filter_type in ['content', 'contains', 'startswith', 'endswith', 'fuzzy']:
                if value.input_type_name == 'exact':
                    query_frag = prepared_value
                else:
                    # Iterate over terms & incorportate the converted form of each into the query.
                    terms = []

                    if isinstance(prepared_value, six.string_types):
                        for possible_value in prepared_value.split(' '):
                            terms.append(filter_types[filter_type] % self.backend._from_python(possible_value))
                    else:
                        terms.append(filter_types[filter_type] % self.backend._from_python(prepared_value))

                    if len(terms) == 1:
                        query_frag = terms[0]
                    else:
                        query_frag = "(%s)" % " AND ".join(terms)
            elif filter_type == 'in':
                in_options = []

                if not prepared_value:
                    query_frag = '(!*:*)'
                else:
                    for possible_value in prepared_value:
                        in_options.append('"%s"' % self.backend._from_python(possible_value))
                    query_frag = "(%s)" % " OR ".join(in_options)

            elif filter_type == 'range':
                start = self.backend._from_python(prepared_value[0])
                end = self.backend._from_python(prepared_value[1])
                query_frag = '["%s" TO "%s"]' % (start, end)
            elif filter_type == 'exact':
                if value.input_type_name == 'exact':
                    query_frag = prepared_value
                else:
                    prepared_value = Exact(prepared_value).prepare(self)
                    query_frag = filter_types[filter_type] % prepared_value
            else:
                if value.input_type_name != 'exact':
                    prepared_value = Exact(prepared_value).prepare(self)

                query_frag = filter_types[filter_type] % prepared_value

        if len(query_frag) and not isinstance(value, Raw):
            if not query_frag.startswith('(') and not query_frag.endswith(')'):
                query_frag = "(%s)" % query_frag

        return "%s%s" % (index_fieldname, query_frag)

    def get_facet_counts(self):
        """
        Returns the facet counts received from the backend.

        If the query has not been run, this will execute the query and store
        the results.

        Customized version.  Like base class get_results() and get_count() check for
        self._raw_query and use run_raw() if not None
        """
        if self._facet_counts is None:
            if self._raw_query:
                # Special case for raw queries.
                self.run_raw()
            else:
                self.run()

        return self._facet_counts

    def run_raw(self, **kwargs):
        """Executes a raw query. Returns a list of search results.

        Customized version.  The raw query is built and then combined with the regular
        query filter.  This allows use of chaining a raw query to apply filters, excludes,
        etc.  The standard Haystack codebase does not support this so we need to prep the
        query the following way:

        sqs = SearchQuerySet()
        sqs.query.raw_search(query_string,params)

        """
        # build raw Query
        query = self._raw_query

        # get additional query
        query_filter = self.build_query()

        # combine
        combined = '({query}) AND {filter}'.format(query=query, filter=query_filter)
        search_kwargs = self.build_params()
        search_kwargs.update(self._raw_query_params)

        if kwargs:
            search_kwargs.update(kwargs)

        results = self.backend.search(combined, **search_kwargs)
        self._results = results.get('results', [])
        self._hit_count = results.get('hits', 0)
        # self._facet_counts = results.get('facets', {})
        self._facet_counts = self.post_process_facets(results)
        self._spelling_suggestion = results.get('spelling_suggestion', None)


class ConfigurableElasticSearchEngine(Elasticsearch6SearchEngine):
    # backend = Elasticsearch5SearchBackend
    backend = ConfigurableElasticsearchBackend
    query = CustomElasticsearchQuery
