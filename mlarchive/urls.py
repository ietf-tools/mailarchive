from django.conf.urls.defaults import *
from django.views.generic.simple import redirect_to

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # default to archive app
    (r'^$', redirect_to, {'url': '/archive/'}),
    (r'^accounts/login/$', 'django.contrib.auth.views.login', {'template_name': 'archive/login.html'}),
    (r'^archive/', include('mlarchive.archive.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # (r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    (r'^admin/', include(admin.site.urls)),
)
