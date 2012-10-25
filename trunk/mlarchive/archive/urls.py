from django.conf.urls.defaults import *
from django.views.generic.simple import direct_to_template
from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.views import CustomSearchView
from haystack.query import SearchQuerySet
from haystack.views import SearchView, search_view_factory


urlpatterns = patterns('mlarchive.archive.ajax',
    url(r'ajax/list/?$', 'ajax_get_list', name='ajax_get_list'),
    url(r'ajax/msg/?$', 'ajax_get_msg', name='ajax_get_msg'),
)

urlpatterns += patterns('mlarchive.archive.views',
    url(r'^$', 'main', name='archive'),
    #url(r'^(?P<list_name>\w+@\w+.\w+)/$', 'browse', name='archive_browse'),
    url(r'^advsearch/', 'advsearch', name='archive_advsearch'),
    url(r'^advsearch2/', 'advsearch2', name='archive_advsearch2'),
    url(r'^browse/$', 'browse', name='archive_browse'),
    url(r'^browse/(?P<list_name>\w+)/', 'browse_list', name='archive_browse_list'),
    url(r'^detail/(?P<id>.+)/$', 'detail', name='archive_detail'),
    url(r'^haystack/', include('haystack.urls'), name='archive_haystack'),
    url(r'^help/$', direct_to_template, {'template':'archive/help.html'}),
    #url(r'^search', 'search', name='archive_search'),
    url(r'^search/', search_view_factory(form_class=AdvancedSearchForm,
                                         view_class=CustomSearchView,
                                         template='archive/search.html'), name='archive_search'),
    (r'^layout/$', direct_to_template, {'template':'archive/layout.html'}),
)


