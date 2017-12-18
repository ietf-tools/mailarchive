from haystack_elasticsearch.elasticsearch5 import (Elasticsearch5SearchBackend,
    Elasticsearch5SearchQuery, Elasticsearch5SearchEngine)

from django.conf import settings


class ConfigurableElasticsearchBackend(Elasticsearch5SearchBackend):
    def build_schema(self, fields):
        content_field_name = 'text'
        mapping = settings.ELASTICSEARCH_INDEX_MAPPINGS

        return (content_field_name, mapping)

class CustomElasticsearchQuery(Elasticsearch5SearchQuery):
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
        combined = u'({query}) AND {filter}'.format(query=query,filter=query_filter)
        search_kwargs = self.build_params()
        search_kwargs.update(self._raw_query_params)

        if kwargs:
            search_kwargs.update(kwargs)

        results = self.backend.search(combined, **search_kwargs)
        self._results = results.get('results', [])
        self._hit_count = results.get('hits', 0)
        #self._facet_counts = results.get('facets', {})
        self._facet_counts = self.post_process_facets(results)
        self._spelling_suggestion = results.get('spelling_suggestion', None)

class ConfigurableElasticSearchEngine(Elasticsearch5SearchEngine):
    backend = ConfigurableElasticsearchBackend
    query = CustomElasticsearchQuery
