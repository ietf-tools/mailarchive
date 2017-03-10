from django.conf import settings
from django.conf.urls import include, url
from django.views.generic import RedirectView

from django.contrib import admin
from django.contrib.auth.views import login

admin.autodiscover()

urlpatterns = [
    url(r'^$', RedirectView.as_view(pattern_name='archive',permanent=True)),
    url(r'^accounts/login/$', login, {'template_name': 'archive/login.html'}),
    url(r'^arch/', include('mlarchive.archive.urls')),
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),
]
