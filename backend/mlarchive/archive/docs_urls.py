from django.urls import path

from django.views.generic import TemplateView


urlpatterns = [
    path('api-reference/', TemplateView.as_view(template_name="archive/api_reference.html"), name="docs_api_reference"),
]
