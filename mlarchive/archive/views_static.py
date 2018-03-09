import codecs
import math
import os
import shutil

from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpRequest
from django.template.loader import render_to_string
from mlarchive.archive import views
from mlarchive.archive.models import EmailList, Message
from mlarchive.utils.test_utils import get_request


THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')


def build_msg_pages(elist):
    """Create static message file"""
    for message in elist.message_set.all().order_by('date'):
        filename = message.hashcode.strip('=') + '.html'
        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
        request = HttpRequest()
        request.method = 'GET'
        request.META = {}
        request = get_request()
        request.META['HTTP_HOST'] = 'mailarchive' + settings.ALLOWED_HOSTS[0]
        response = views.detail(request, list_name=elist.name, id=message.hashcode)
        with codecs.open(path, 'w', 'utf8') as file:
            file.write(response.content.decode('utf8'))


def update_static_index(elist):
    """Update static index pages for list.  Find unindexed messages, date_index_page == 0,
    and build all pages necessary"""
    oldest = elist.message_set.filter(date_index_page='').order_by('date').first()
    if not oldest:
        return
    older = elist.message_set.filter(date__lte=oldest.date)
    page = int(math.ceil(older.count() / float(settings.STATIC_INDEX_MESSAGES_PER_PAGE)))
    build_date_pages(elist, start=page)

    messages = elist.message_set.filter(thread_index_page='').order_by(*THREAD_SORT_FIELDS)
    messages.reverse()
    # for m in messages: print m.date, m.thread
    oldest = messages.first()
    older = elist.message_set.filter(thread__date__lte=oldest.thread.date)
    page = int(math.ceil(older.count() / float(settings.STATIC_INDEX_MESSAGES_PER_PAGE)))
    # assert False, (oldest.date, older, page)
    build_thread_pages(elist, start=page)


def rebuild_static_index(elist=None, resume=False):
    """Rebuilds static index pages for public lists.
    elist: rebuild specified list only
    resume: start full rebuild at given list"""
    assert 'static' in settings.STATIC_INDEX_DIR    # extra precaution before removing
    if elist and not resume:
        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name)
        assert not elist.private
        elists = [elist]
        if os.path.exists(path):
            shutil.rmtree(path)
    elif elist and resume:
        elists = EmailList.objects.filter(private=False, name__gte=elist.name).order_by('name')
    else:
        elists = EmailList.objects.filter(private=False).order_by('name')
        if os.path.exists(settings.STATIC_INDEX_DIR):
            shutil.rmtree(settings.STATIC_INDEX_DIR)
        os.mkdir(settings.STATIC_INDEX_DIR)

    for elist in elists:
        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name)
        if not os.path.isdir(path):
            os.mkdir(path)
        build_index_page(elist)
        build_date_pages(elist)
        build_thread_pages(elist)
        build_msg_pages(elist)


def build_index_page(elist):
    """Create the index.html"""
    index_path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, 'index.html')
    content = render_to_string('archive/static_index_index.html', {'url': 'maillist.html'})
    with codecs.open(index_path, 'w', 'utf8') as index_file:
        index_file.write(content)


def build_date_pages(elist, start=1):
    messages = elist.message_set.order_by('date')
    paginator = Paginator(messages, settings.STATIC_INDEX_MESSAGES_PER_PAGE)
    for page_number in xrange(start, paginator.num_pages + 1):
        page = paginator.page(page_number)
        if page_number == paginator.num_pages:
            filename = 'maillist.html'
        else:
            filename = 'mail{page_number:04d}.html'.format(page_number=page_number)

        queryset = Message.objects.filter(id__in=[m.id for m in page.object_list])
        queryset.update(date_index_page=filename)

        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
        content = render_to_string('archive/static_index_date.html', {'page': page})
        with codecs.open(path, 'w', 'utf8') as static_file:
            static_file.write(content)


def build_thread_pages(elist, start=1):
    messages = list(elist.message_set.order_by(*THREAD_SORT_FIELDS))
    messages.reverse()
    paginator = Paginator(messages, settings.STATIC_INDEX_MESSAGES_PER_PAGE)
    for page_number in xrange(start, paginator.num_pages + 1):
        page = paginator.page(page_number)
        if page_number == paginator.num_pages:
            filename = 'threadlist.html'
        else:
            filename = 'thread{page_number:04d}.html'.format(page_number=page_number)

        queryset = Message.objects.filter(id__in=[m.id for m in page.object_list])
        queryset.update(thread_index_page=filename)

        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
        content = render_to_string('archive/static_index_thread.html', {'page': page})
        with codecs.open(path, 'w', 'utf8') as static_file:
            static_file.write(content)
