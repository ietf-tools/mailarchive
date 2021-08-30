from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import path 
from django.views.generic import TemplateView
# from haystack.views import search_view_factory

from mlarchive.archive import ajax
from mlarchive.archive import views


urlpatterns = [
    path('ajax/msg/', ajax.ajax_get_msg, name='ajax_get_msg'),
    path('ajax/messages/', ajax.ajax_messages, name='ajax_messages'),
    path('ajax/admin/action/', ajax.ajax_admin_action, name='ajax_admin_action'),

    path('', views.main, name='archive'),
    path('admin/', views.admin, name='archive_admin'),
    path('admin/guide/', views.admin_guide, name='archive_admin_guide'),
    path('admin/console/', views.admin_console, name='archive_admin_console'),
    path('advsearch/', views.advsearch, name='archive_advsearch'),
    path('browse/', views.browse, name='archive_browse'),
    path('browse/static/', views.browse_static, name='archive_browse_static'),
    path('browse/<list_name>/', views.CustomBrowseView.as_view(), name='archive_browse_list'),
    path('browse/static/<list_name>/', views.browse_static_redirect, name='archive_browse_static'),
    path('browse/static/<list_name>/thread/', views.browse_static_thread_redirect, name='archive_browse_static_thread_redirect'),
    path('browse/static/<list_name>/<date>/', views.DateStaticIndexView.as_view(), name='archive_browse_static_date'),
    path('browse/static/<list_name>/thread/<date>/', views.ThreadStaticIndexView.as_view(), name='archive_browse_static_thread'),
    path('export/<type>/', views.export, name='archive_export'),
    path('help/', TemplateView.as_view(template_name="archive/help.html"), name='archive_help'),
    path('legacy/msg/<list_name>/<id>/', views.legacy_message, name='archive_legacy_message'),
    path('logout/', views.logout_view, name='archive_logout'),
    # url(r'^msg/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[a-zA-Z0-9_\-]+)(=)?(/)?$', views.detail, name='archive_detail'),
    # url(r'^msg/(?P<list_name>[a-z0-9_\-\+]+)/(?P<id>[a-zA-Z0-9_\-]+)(=)?/(?P<sequence>\d+)(/)?$', views.attachment, name='a
    path('msg/<list_name>/<id>/', views.detail, name='archive_detail'),
    path('msg/<list_name>/<id>/<int:sequence>/', views.attachment, name='archive_attachment'),
    path('search/', views.CustomSearchView.as_view(), name='archive_search'),
    # test pages ----------------
]
