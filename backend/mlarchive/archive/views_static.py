import datetime
import codecs
import math
import os
import shutil
from collections import namedtuple

from django.conf import settings
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from mlarchive.archive import views
from mlarchive.archive.models import EmailList, Message
from mlarchive.utils.test_utils import get_request


THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
EMPTY_QUERYSET = Message.objects.none()
TimePeriod = namedtuple('TimePeriod', 'year, month')

'''
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
    # get oldest page, date or thread
    # call build_static_pages

    messages = elist.message_set.filter(thread_index_page='').order_by(*THREAD_SORT_FIELDS)
    messages.reverse()
    # for m in messages: print m.date, m.thread
    oldest = messages.first()
    older = elist.message_set.filter(thread__date__lte=oldest.thread.date)
    page = int(math.ceil(older.count() / float(settings.STATIC_INDEX_MESSAGES_PER_PAGE)))
    # assert False, (oldest.date, older, page)
    build_static_pages(elist, start=page)
'''


def update_static_index(elist):
    # TODO: remove this if we're using a cache
    pass


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
        build_static_pages(elist)
        link_index_page(elist)


def build_static_pages(elist, start=None):
    """Calls browse_static view for all appropriate date periods and writes content
    to data/static directory
    """
    if elist.message_set.count() == 0:
        return
    messages = elist.message_set.order_by('date')
    if not start:
        start = messages.first()
    end = messages.last()
    for year in range(start.date.year, end.date.year + 1):
        request = get_request()
        request.META['HTTP_HOST'] = 'mailarchive' + settings.ALLOWED_HOSTS[0]
        date = '{}'.format(year)
        date_view = views.DateStaticIndexView.as_view()
        thread_view = views.ThreadStaticIndexView.as_view()
        # build date index page
        response = date_view(request, list_name=elist.name, date=date)
        write_index(elist, date, response.content)
        
        # build thread index page
        response = thread_view(request, list_name=elist.name, date=date)
        write_index(elist, 'thread' + date, response.content)

        for month in range(1, 13):
            month_date = '{}-{:02d}'.format(year, month)
            # build date index page
            response = date_view(request, list_name=elist.name, date=month_date)
            write_index(elist, month_date, response.content)
            
            # build thread index page
            response = thread_view(request, list_name=elist.name, date=month_date)
            write_index(elist, 'thread' + month_date, response.content)
            
            # break if reached month of last message
            if end.date.year == year and end.date.month == month:
                break


def write_index(elist, name, content):
    filename = name + '.html'
    path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
    with codecs.open(path, 'w', 'utf8') as static_file:
        static_file.write(content)


def link_index_page(elist):
    path = os.path.join(settings.STATIC_INDEX_DIR, elist.name)
    if not os.listdir(path):
        return
    message = elist.message_set.order_by('date').last()
    source = get_index_file(message)
    link_name = os.path.join(path, 'index.html')
    if os.path.exists(link_name):
        os.remove(link_name)
    os.link(source, link_name)
    
    thread = elist.thread_set.order_by('date').last()
    message = thread.first
    source = get_index_file(message, prefix='thread')
    link_name = os.path.join(path, 'thread.html')
    if os.path.exists(link_name):
        os.remove(link_name)
    print(source)
    os.link(source, link_name)


def get_index_file(message, prefix=''):
    path = os.path.join(settings.STATIC_INDEX_DIR, message.email_list.name)
    today = datetime.datetime.today()
    if message.date.year != today.year and is_small_year(message.email_list, message.date.year):
        source = os.path.join(path, '{}{}.html'.format(prefix, message.date.year))
    else:
        source = os.path.join(path, '{}{}-{:02d}.html'.format(prefix, message.date.year, message.date.month))
    return source


def is_small_year(email_list, year):
    count = Message.objects.filter(email_list=email_list, date__year=year).count()
    return count < settings.STATIC_INDEX_YEAR_MINIMUM
