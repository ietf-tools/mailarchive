# Copyright The IETF Trust 2026, All Rights Reserved

from urllib.parse import urlparse

import typesense
from typesense.exceptions import ObjectNotFound

from django.conf import settings

from ..base import BaseSearchBackend


def prepare_message(message) -> dict:
    """Convert an archive.Message instance to a dict matching TYPESENSE_SCHEMA."""
    return {
        'id': str(message.pk),
        'django_ct': 'archive.message',
        'django_id': int(message.pk),
        'date': int(message.date.timestamp()),
        'email_list': message.email_list.name,
        'frm': message.frm,
        'frm_name': message.frm_name,
        'msgid': message.msgid,
        'subject': message.subject,
        'subject_base': message.base_subject,
        'text': '\n'.join([message.frm, message.subject, message.get_body()]),
        'thread_date': int(message.thread_date.timestamp()),
        'thread_depth': message.thread_depth,
        'thread_id': message.thread_id,
        'thread_order': message.thread_order,
        'spam_score': message.spam_score,
        'url': message.get_absolute_url(),
    }


class TypesenseSearchBackend(BaseSearchBackend):
    def __init__(self, alias='default'):
        config = settings.SEARCH_BACKENDS[alias]
        parsed = urlparse(config['URL'])
        self.client = typesense.Client({
            'nodes': [{
                'host': parsed.hostname,
                'port': parsed.port or (443 if parsed.scheme == 'https' else 80),
                'protocol': parsed.scheme,
            }],
            'api_key': config['API_KEY'],
            'connection_timeout_seconds': 2,
        })
        self.schema = config['SCHEMA']
        self.collection_name = self.schema['name']
        self.setup_complete = False

    def setup(self):
        """Create the Typesense collection if it does not already exist."""
        try:
            self.client.collections[self.collection_name].retrieve()
        except ObjectNotFound:
            self.client.collections.create(self.schema)
        self.setup_complete = True

    def update(self, document: dict) -> None:
        """Upsert a document into the Typesense collection."""
        if not self.setup_complete:
            self.setup()
        self.client.collections[self.collection_name].documents.upsert(document)

    def remove(self, id: str) -> None:
        """Delete a document by id. No-op if the document does not exist."""
        if not self.setup_complete:
            self.setup()
        try:
            self.client.collections[self.collection_name].documents[id].delete()
        except ObjectNotFound:
            pass

    def clear(self) -> None:
        """Delete the collection and recreate it empty."""
        try:
            self.client.collections[self.collection_name].delete()
        except ObjectNotFound:
            pass
        self.setup_complete = False
        self.setup()

    def search(self, query: str, limit: int = 10, **kwargs) -> list:
        """Search the Typesense collection. Returns the list of hits.

        Each hit is a dict with keys 'document', 'highlight', 'text_match',
        etc. Extra kwargs (e.g. query_by, filter_by, sort_by, facet_by) are
        passed through as Typesense search parameters.
        """
        if not self.setup_complete:
            self.setup()
        params = {
            'q': query,
            'query_by': 'text',
            'per_page': limit,
        }
        params.update(kwargs)
        results = self.client.collections[self.collection_name].documents.search(params)
        return results['hits']
