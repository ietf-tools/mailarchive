# sitemaps.py
from django.contrib import sitemaps
from django.urls import reverse

from mlarchive.archive.models import EmailList, Message


class StaticViewSitemap(sitemaps.Sitemap):
    priority = 0.5
    changefreq = 'weekly'
    protocol = 'https'

    def items(self):
        items = [('archive', {}), ('archive_browse', {})]
        for elist in EmailList.objects.filter(private=False):
            if elist.message_set.count() == 0:
                continue
            kwargs = {}
            kwargs['list_name'] = elist.name
            items.append(('archive_browse_static_date', kwargs))
        return items

    def location(self, item):
        if item[0] == 'archive_browse_static_date':
            last_message = Message.objects.filter(email_list__name=item[1]['list_name']).order_by('-date').first()
            return last_message.get_static_date_page_url()
        return reverse(item[0], kwargs=item[1])
