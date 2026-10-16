# sitemaps.py
import datetime

from django.conf import settings
from django.contrib import sitemaps
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import TruncYear
from django.urls import reverse

from mlarchive.archive.models import EmailList, Message


class StaticViewSitemap(sitemaps.Sitemap):
    priority = 0.5
    changefreq = 'weekly'
    protocol = 'https'

    def items(self):
        latest = Message.objects.filter(email_list=OuterRef('pk')).order_by('-date').values('date')[:1]
        last_year_count = (Message.objects
                           .filter(email_list=OuterRef('pk'), date__gte=OuterRef('last_year_start'))
                           .order_by().values('email_list').annotate(count=Count('*')).values('count'))
        lists = (EmailList.objects.filter(private=False)
                 .annotate(last_date=Subquery(latest))
                 .exclude(last_date=None)
                 .annotate(last_year_start=TruncYear('last_date'))
                 .annotate(last_year_count=Subquery(last_year_count))
                 .order_by('name'))
        return ['archive', 'archive_browse'] + list(lists)

    def location(self, item):
        if isinstance(item, EmailList):
            return reverse('archive_browse_static_date',
                           kwargs={'list_name': item.name, 'date': static_date(item)})
        return reverse(item)


def static_date(elist):
    """Returns the date part of the static date page URL for the list's last message.

    Same rule as Message.get_static_date_page_url().
    """
    last_date = elist.last_date
    if (last_date.year < datetime.datetime.today().year
            and elist.last_year_count < settings.STATIC_INDEX_YEAR_MINIMUM):
        return '{}'.format(last_date.year)
    return '{}-{:02d}'.format(last_date.year, last_date.month)
