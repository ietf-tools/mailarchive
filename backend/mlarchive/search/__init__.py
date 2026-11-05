# Copyright The IETF Trust 2026, All Rights Reserved

from django.conf import settings


def get_search_backend(alias='default'):
    config = settings.SEARCH_BACKENDS[alias]
    engine = config['ENGINE']
    if engine == 'typesense':
        from .backends.typesense import TypesenseSearchBackend
        return TypesenseSearchBackend(alias=alias)
    elif engine == 'elasticsearch':
        from .backends.elasticsearch import ElasticSearchBackend
        return ElasticSearchBackend(alias=alias)
    raise ValueError(f"Unknown search engine: {engine!r}")
