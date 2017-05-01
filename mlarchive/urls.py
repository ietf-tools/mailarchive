from django.conf import settings
from django.conf.urls import include, url
from django.views.generic import RedirectView

from django.contrib import admin
from django.contrib.auth import views as auth_views

admin.autodiscover()

urlpatterns = [
    url(r'^$', RedirectView.as_view(pattern_name='archive',permanent=True)),
    url(r'^accounts/login/$', auth_views.LoginView.as_view(template_name='archive/login.html')),
    url(r'^arch/', include('mlarchive.archive.urls')),
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns