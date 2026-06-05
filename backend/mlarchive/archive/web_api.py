"""Browser-facing JSON API for the Nuxt frontend.

These endpoints live under ``/arch/api/v1/`` and are authenticated with the
normal Django *session cookie* (and CSRF for any future writes).  They are
deliberately separate from the machine API in ``api.py`` (mounted at
``/api/v1/``), which uses X-API-KEY auth and is ``csrf_exempt``.

Each view is a thin wrapper that reuses the existing archive logic
(``search_from_form``, ``CustomPaginator``, ``Message`` helpers, the access
decorators) and returns JSON, so authorization is identical to the
server-rendered pages these endpoints mirror.
"""
import datetime

from django.conf import settings
from django.core.paginator import InvalidPage
from django.db.models import Count
from django.http import JsonResponse

from elasticsearch.exceptions import RequestError

from mlarchive.exceptions import HttpJson400, HttpJson404
from mlarchive.archive.models import EmailList
from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.backends.elasticsearch import search_from_form
from mlarchive.archive.query_utils import CustomPaginator, get_count
from mlarchive.archive.utils import get_lists_for_user
from mlarchive.utils.decorators import pad_id, check_access

import logging
logger = logging.getLogger(__name__)


# --------------------------------------------------------
# Serializers
# --------------------------------------------------------


def _iso(value):
    """Coerce a date/datetime (or already-formatted string) to ISO text."""
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value or ''


def serialize_hit(hit):
    """Serialize an Elasticsearch search hit (fields from ``full_prepare``)."""
    return {
        'url': getattr(hit, 'url', ''),
        'msgid': getattr(hit, 'msgid', ''),
        'subject': getattr(hit, 'subject', ''),
        'frm': getattr(hit, 'frm', ''),
        'frm_name': getattr(hit, 'frm_name', ''),
        'date': _iso(getattr(hit, 'date', '')),
        'email_list': getattr(hit, 'email_list', ''),
        'thread_id': getattr(hit, 'thread_id', None),
        'thread_depth': getattr(hit, 'thread_depth', 0),
        'django_id': getattr(hit, 'django_id', ''),
    }


def serialize_aggregations(response):
    """Flatten the ``list_terms``/``from_terms`` bucket aggregations."""
    aggs = {}
    raw = response.aggregations.to_dict() if hasattr(response, 'aggregations') else {}
    for name in ('list_terms', 'from_terms'):
        bucket = raw.get(name)
        if bucket:
            aggs[name] = [
                {'key': b['key'], 'doc_count': b['doc_count']}
                for b in bucket.get('buckets', [])
            ]
    return aggs


def _nav_url(message):
    return message.get_absolute_url() if message else ''


def serialize_message_detail(msg, request=None):
    """Full message-detail payload, mirroring ``Message.as_json`` but with the
    email list *name* (not pk) and rendered body/thread HTML."""
    return {
        'msgid': msg.msgid,
        'subject': msg.subject,
        'frm': msg.frm,
        'frm_name': msg.frm_name,
        'to': msg.to,
        'cc': msg.cc,
        'date': _iso(msg.date),
        'email_list': msg.email_list.name,
        'list_private': msg.email_list.private,
        'url': msg.get_absolute_url(),
        'download_url': msg.get_download_url(),
        'thread_id': msg.thread_id,
        'thread_depth': msg.thread_depth,
        'body': msg.get_body_html(request=request),
        'thread_snippet': msg.get_thread_snippet(),
        'date_index_url': msg.get_date_index_url(),
        'thread_index_url': msg.get_thread_index_url(),
        'nav': {
            'previous_in_list': _nav_url(msg.previous_in_list()),
            'next_in_list': _nav_url(msg.next_in_list()),
            'previous_in_thread': _nav_url(msg.previous_in_thread()),
            'next_in_thread': _nav_url(msg.next_in_thread()),
        },
    }


# --------------------------------------------------------
# Views
# --------------------------------------------------------


def whoami(request):
    """Return the current user's authentication state so the UI can reflect it.
    Authorization itself always stays server-side in Django."""
    user = request.user
    return JsonResponse({
        'authenticated': user.is_authenticated,
        'username': user.get_username() if user.is_authenticated else '',
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
    })


def lists(request):
    """Return the email lists the user may view, with message counts.
    Private-list visibility is enforced by ``get_lists_for_user``."""
    names = get_lists_for_user(request.user)
    qs = (EmailList.objects
          .filter(name__in=list(names))
          .annotate(message_count=Count('message'))
          .order_by('name'))
    data = [{
        'name': el.name,
        'description': el.description,
        'private': el.private,
        'active': el.active,
        'message_count': el.message_count,
    } for el in qs]
    return JsonResponse({'lists': data})


def search(request):
    """Run an Elasticsearch query built from the same GET params the
    server-rendered search page uses, returning hits, facets and pagination."""
    data = request.GET if len(request.GET) else None
    form = AdvancedSearchForm(data, request=request)
    es_search = search_from_form(form)

    try:
        page_no = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        raise HttpJson400('invalid page number')
    if page_no < 1:
        raise HttpJson400('page number must be 1 or greater')

    paginator = CustomPaginator(es_search, settings.ELASTICSEARCH_RESULTS_PER_PAGE)
    try:
        page = paginator.page(page_no)
        response = page.object_list
        count = get_count(es_search)
        results = [serialize_hit(hit) for hit in response]
        aggregations = serialize_aggregations(response)
    except InvalidPage:
        raise HttpJson404('no such page')
    except RequestError:
        raise HttpJson400('invalid search expression')

    return JsonResponse({
        'results': results,
        'aggregations': aggregations,
        'count': count,
        'page': page_no,
        'num_pages': paginator.num_pages,
        'has_next': page.has_next(),
        'has_previous': page.has_previous(),
        'results_per_page': settings.ELASTICSEARCH_RESULTS_PER_PAGE,
        'group_by_thread': bool(request.GET.get('gbt')),
        'queryid': getattr(es_search, 'queryid', None),
    })


@pad_id
@check_access
def message_detail(request, list_name, id, msg):
    """Return a single message as JSON.

    The ``@check_access`` decorator adds the ``msg`` argument and handles
    private-list 403, moved-message 301 redirects, and removed-message 410
    exactly as the HTML detail view does, so this endpoint inherits all of
    that behavior unchanged.
    """
    return JsonResponse(serialize_message_detail(msg, request=request))
