from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url
from django.views.generic import TemplateView
from haystack.views import search_view_factory

from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive import ajax
from mlarchive.archive import views
from mlarchive.archive.view_funcs import custom_search_view_factory


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
    url(r'^browse/(?P<list_name>[a-z0-9_\-\+\.]+)/$', custom_search_view_factory(
        form_class=AdvancedSearchForm,
        view_class=views.CustomBrowseView,
        template='archive/search.html'), name='archive_browse_list'),
    url(r'^browse/static/(?P<list_name>[a-z0-9_\-\+\.]+)/$', views.browse_static_redirect, name='archive_browse_static'),
    url(r'^browse/static/(?P<list_name>[a-z0-9_\-\+\.]+)/thread/$', views.browse_static_thread_redirect, name='archive_browse_static_thread_redirect'),
    url(r'^browse/static/(?P<list_name>[a-z0-9_\-\+\.]+)/(?P<date>\d{4}(-\d{2})?)/$', views.DateStaticIndexView.as_view(), name='archive_browse_static_date'),
    url(r'^browse/static/(?P<list_name>[a-z0-9_\-\+\.]+)/thread/(?P<date>\d{4}(-\d{2})?)/$', views.ThreadStaticIndexView.as_view(), name='archive_browse_static_thread'),
    url(r'^export/(?P<type>mbox|maildir|url)/', views.export, name='archive_export'),
    url(r'^help/$', TemplateView.as_view(template_name="archive/help.html"), name='archive_help'),
    url(r'^legacy/msg/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[0-9]+)/$', views.legacy_message, name='archive_legacy_message'),
    url(r'^logout/$', views.logout_view, name='archive_logout'),
    url(r'^msg/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[a-zA-Z0-9_\-]+)(=)?(/)?$', views.detail, name='archive_detail'),
    # url(r'^msg/classic/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[a-zA-Z0-9_\-]+)(=)?(/)?$', views.detail_classic, name='archive_detail_classic'),
    url(r'^search/', search_view_factory(
        form_class=AdvancedSearchForm,
        view_class=views.CustomSearchView,
        template='archive/search.html'), name='archive_search'),

    # test pages ----------------
    # (r'^layout/$', TemplateView.as_view(template_name="archive/layout.html")),
    # (r'^test/$', TemplateView.as_view(template_name="archive/test.html")),
    # url(r'^test/msg/(?P<pk>[0-9]+)/$', views.MessageDetailView.as_view(), name='archive_test_blob'),
    # url(r'^msgx/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[a-zA-Z0-9_\-]+)(=)?(/)?$', views.detailx, name='archive_detailx'),
]
