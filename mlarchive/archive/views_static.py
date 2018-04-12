import codecs
import math
import os
import shutil
from datetime import datetime, timedelta

from django.conf import settings
#from django.core.paginator import Paginator, Page
from django.http import HttpRequest
from django.template.loader import render_to_string
#from django.utils.functional import cached_property
from django.urls import reverse
from mlarchive.archive import views
from mlarchive.archive.models import EmailList, Message
from mlarchive.utils.test_utils import get_request


THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
EMPTY_QUERYSET = Message.objects.none()

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
        build_date_pages(elist)
        # build_thread_pages(elist)
        # build_msg_pages(elist)
        build_index_page(elist)


def build_index_page(elist):
    """Create the index.html"""
    path = os.path.join(settings.STATIC_INDEX_DIR, elist.name)
    url = sorted(os.listdir(path))[-1]
    content = render_to_string('archive/refresh.html', {'url': url})
    write_index(elist, 'index', content)


"""
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


def build_date_pages(elist, start=1):
    paginator = CustomPaginator(elist.message_set.all(), settings.STATIC_INDEX_YEAR_MINIMUM)
    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        filename = page.page_name + '.html'
        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
        if page.refresh_url:
            # content = 
            pass
        else:
            content = render_to_string('archive/static_index_date.html', {'page': page})
        with codecs.open(path, 'w', 'utf8') as static_file:
            static_file.write(content)
"""


def build_date_pages(elist, start=None):
    messages = elist.message_set.order_by('date')
    if not start:
        start = messages.first()
    end = messages.last()
    for year in range(start.date.year, end.date.year + 1):
        content = get_year_page(elist, year)
        write_index(elist, str(year), content)
        for month in range(1, 13):
            content = get_month_page(elist, month, year)
            write_index(elist, '{}-{:02d}'.format(year, month), content)


def get_year_page(elist, year):
    queryset = elist.message_set.filter(date__year=year).order_by('date')
    count = queryset.count()
    next_message = elist.message_set.filter(date__year__gt=year).order_by('date').first()
    if next_message is None:
        next_page = ''
    else:
        next_page = str(next_message.date.year)
    previous_message = elist.message_set.filter(date__year__lt=year).order_by('date').last()
    if previous_message is None:
        previous_page = ''
    else:
        previous_page = previous_message.date.strftime("%Y-%m")
    context = {'next_page': next_page, 'previous_page': previous_page}

    if count == 0:
        context['queryset'] = Message.objects.none(),
        return render_to_string('archive/static_index_date.html', context)
    elif count < settings.STATIC_INDEX_YEAR_MINIMUM:
        context['queryset'] = queryset
        return render_to_string('archive/static_index_date.html', context)
    else:
        # redirect to first month page
        name = queryset.first().date.strftime("%Y-%m")
        url = reverse('archive_browse_static', kwargs={'list_name': elist.name}) + name
        return render_to_string('archive/refresh.html', {'url': url})


def get_month_page(elist, month, year):
    year_count = elist.message_set.filter(date__year=year).count()
    this_month = datetime(year, month, 1)
    next_month = add_one_month(this_month)
    if year_count < settings.STATIC_INDEX_YEAR_MINIMUM:
        name = str(year)
        url = reverse('archive_browse_static', kwargs={'list_name': elist.name}) + name
        return render_to_string('archive/refresh.html', {'url': url})

    queryset = elist.message_set.filter(date__year=year, date__month=month).order_by('date')
    next_message = elist.message_set.filter(date__gte=next_month).order_by('date').first()
    if next_message:
        next_page = next_message.date.strftime("%Y-%m")
    else:
        next_page = ''
    previous_message = elist.message_set.filter(date__lt=this_month).order_by('-date').first()
    if previous_message:
        previous_page = previous_message.date.strftime("%Y-%m")
    else:
        previous_page = ''
    context = {'queryset': queryset, 'next_page': next_page, 'previous_page': previous_page}
    return render_to_string('archive/static_index_date.html', context)


def write_index(elist, name, content):
    filename = name + '.html'
    path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
    with codecs.open(path, 'w', 'utf8') as static_file:
        static_file.write(content)

def add_one_month(dt0):
    dt1 = dt0.replace(day=1)
    dt2 = dt1 + timedelta(days=32)
    dt3 = dt2.replace(day=1)
    return dt3

'''
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


def messages_by_year(messages):
    """A generator which yields querysets of messages by year"""
    first = messages.order_by('date').first()
    now = datetime.datetime.now()
    for year in range(first.date.year, now.year + 1):
        chunk = messages.filter(date__year=year)
        if chunk.count() > 0:
            yield chunk


class CustomPaginator(Paginator):
    """A Custom Paginator object that builds pages of messages by the year if less than
    per_year, otherwise by month

    self.pages is a list of tuples (queryset, name) used to build page objects
    """

    def __init__(self, queryset, per_year):
        self.queryset = queryset.order_by('date')
        self.count = queryset.count()
        self.per_year = int(per_year)
        self.pages = self.build_pages()
        self.fill_pages()
        # self.order_pages()

    def build_pages(self):
        pages = collections.OrderDict()
        first = self.queryset.first()
        last = self.queryset.last()
        for year in range(first.date.year, last.date.year + 1):
            chunk = self.queryset.filter(date__year=year)
            if 0 < chunk.count() < self.per_year:
                pages[str(year)] = {'queryset': chunk}
            elif chunk.count() >= self.per_year:
                for month in range(1, 13):
                    chunk = self.queryset.filter(date__year=year, date__month=month)
                    if chunk.count() > 0:
                        pages['{}-{:02d}'.format(year, month)] = {'queryset': chunk}
        return pages

    def fill_pages(self):
        """Add no content pages with appropriate links"""

        real_pages = self.pages.items()
        first = self.queryset.first()
        last = self.queryset.last()
        previous_page = None
        next_page = 0

        for year in range(first.date.year, last.year + 1):
            if not self.pages[str(year)]:
                # if there's a month this year, set refresh_url
                if real_pages[next_page][0][:4] == str(year):
                    self.pages[year] = {'refresh_url': real_pages[next_page][0]}
                # else empty page with next pointing to next real page
                else:
                    self.pages[year] = {
                        'queryset': EMPTY_QUERYSET,
                        'next_name': ,
                        'previous_name': }

            for month in range(1, 13):
                if not self.pages['{}-{:02d}'.format(year, month)]:
                    # if < min year, refresh to year
                    # else empty page point to next real page, previous last real page

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """
        number = self.validate_number(number)
        page_info = self.pages[number]
        return self._get_page(page_info.queryset, page_info.name, number, self)

    def _get_page(self, *args, **kwargs):
        """
        Returns an instance of a single page.

        This hook can be used by subclasses to use an alternative to the
        standard :cls:`Page` object.
        """
        return CustomPage(*args, **kwargs)

    @cached_property
    def num_pages(self):
        """
        Returns the total number of pages.
        """
        return len(self.pages)


class CustomPage(Page):
    def __init__(self, object_list, number, name, paginator):
        self.object_list = object_list
        self.number = number
        self.name = name
        self.paginator = paginator

    def page_name(self):
        return self.name

    def next_page_name(self):
        return self.paginator.page(self.next_page_number).page_name

    def previous_page_name(self):
        return self.paginator.page(self.previous_page_number).page_name
'''