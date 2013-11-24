from django.conf.urls import patterns, include, url
from django.views.generic import RedirectView

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    (r'^$', RedirectView.as_view(url='/archive/')),
    (r'^accounts/login/$', 'django.contrib.auth.views.login', {'template_name': 'archive/login.html'}),
    (r'^archive/', include('mlarchive.archive.urls')),
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    (r'^admin/', include(admin.site.urls)),
)
