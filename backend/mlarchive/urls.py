from django.conf import settings
from django.urls import include, path
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
    path('', RedirectView.as_view(pattern_name='archive',permanent=True)),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='archive/login.html'), name='login'),
    path('arch/', include('mlarchive.archive.urls')),
    path('admin/', admin.site.urls),
    path('sitemap\.xml', cache_page(86400)(gzip_page(sitemap)), {'sitemaps': sitemaps},
        name='django.contrib.sitemaps.views.sitemap'),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
