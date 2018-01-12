from django.conf.urls import url
from django.views.generic import TemplateView
from haystack.views import search_view_factory

from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive import ajax
from mlarchive.archive import views


urlpatterns = [
    url(r'ajax/msg/?$', ajax.ajax_get_msg, name='ajax_get_msg'),
    url(r'ajax/messages/?$', ajax.ajax_messages, name='ajax_messages'),
    url(r'ajax/admin/action/$', ajax.ajax_admin_action, name='ajax_admin_action'),

    url(r'^$', views.main, name='archive'),
    url(r'^admin/$', views.admin, name='archive_admin'),
    url(r'^admin/guide/$', views.admin_guide, name='archive_admin_guide'),
    url(r'^admin/console/$', views.admin_console, name='archive_admin_console'),
    url(r'^advsearch/', views.advsearch, name='archive_advsearch'),
    url(r'^browse/$', views.browse, name='archive_browse'),
    url(r'^browse/(?P<list_name>[a-z0-9_\-\+]+)/$', views.browse, name='archive_browse_redirect'),
    # url(r'^browse/(?P<list_name>\w+)/', views.browse_list, name='archive_browse_list'),
    url(r'^export/(?P<type>mbox|maildir|url)/', views.export, name='archive_export'),
    url(r'^help/$', TemplateView.as_view(template_name="archive/help.html"), name='archive_help'),
    url(r'^legacy/msg/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[0-9]+)/$',
        views.legacy_message,
        name='archive_legacy_message'),
    url(r'^logout/$', views.logout_view, name='archive_logout'),
    url(r'^msg/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[a-zA-Z0-9_\-]+)(=)?(/)?$', views.detail, name='archive_detail'),
    url(r'^search/', search_view_factory(form_class=AdvancedSearchForm,
                                         view_class=views.CustomSearchView,
                                         template='archive/search.html'), name='archive_search'),

    # test pages ----------------
    # (r'^layout/$', TemplateView.as_view(template_name="archive/layout.html")),
    # (r'^test/$', TemplateView.as_view(template_name="archive/test.html")),
]
