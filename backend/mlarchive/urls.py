from django.conf import settings
from django.conf.urls import include, url
from django.views.generic import RedirectView

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps.views import sitemap
from django.views.decorators.cache import cache_page
from django.views.decorators.gzip import gzip_page

from .sitemaps import StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap,
}

admin.autodiscover()

urlpatterns = [
    url(r'^$', RedirectView.as_view(pattern_name='archive',permanent=True)),
    url(r'^accounts/login/$', auth_views.LoginView.as_view(template_name='archive/login.html'), name='login'),
    url(r'^arch/', include('mlarchive.archive.urls')),
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', admin.site.urls),
    url(r'^sitemap\.xml$', cache_page(86400)(gzip_page(sitemap)), {'sitemaps': sitemaps},
        name='django.contrib.sitemaps.views.sitemap'),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
