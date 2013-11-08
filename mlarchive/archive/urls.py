from django.conf.urls.defaults import *
from django.views.generic import TemplateView
from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.views import CustomSearchView
from haystack.views import search_view_factory


urlpatterns = patterns('mlarchive.archive.ajax',
    url(r'ajax/list/?$', 'ajax_get_list', name='ajax_get_list'),
    url(r'ajax/msg/?$', 'ajax_get_msg', name='ajax_get_msg'),
    url(r'ajax/messages/?$', 'ajax_messages', name='ajax_messages'),
)

urlpatterns += patterns('mlarchive.archive.views',
    url(r'^$', 'main', name='archive'),
    #url(r'^(?P<list_name>\w+@\w+.\w+)/$', 'browse', name='archive_browse'),
    url(r'^admin/$', 'admin', name='archive_admin'),
    url(r'^advsearch/', 'advsearch', name='archive_advsearch'),
    url(r'^browse/$', 'browse', name='archive_browse'),
    url(r'^browse/(?P<list_name>\w+)/', 'browse_list', name='archive_browse_list'),
    url(r'^console/$', 'console', name='archive_console'),
    url(r'^detail/(?P<list_name>[a-z0-9_\-]+)/(?P<id>[a-zA-Z0-9_\-\=]+)/$', 'detail', name='archive_detail'),
    url(r'^export/(?P<type>mbox|maildir)/', 'export', name='archive_export'),
    url(r'^help/$', TemplateView.as_view(template_name="archive/help.html")),
    url(r'^logout/$', 'logout_view', name='archive_logout'),
    url(r'^search/', search_view_factory(form_class=AdvancedSearchForm,
                                         view_class=CustomSearchView,
                                         template='archive/search.html'), name='archive_search'),

    # test pages ----------------
    (r'^layout/$', TemplateView.as_view(template_name="archive/layout.html")),
    #(r'^test/$', direct_to_template, {'template':'archive/test.html'}),
    (r'^test/$', 'test'),
)


