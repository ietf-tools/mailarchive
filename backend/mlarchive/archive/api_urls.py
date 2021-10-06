from django.urls import path

from mlarchive.archive import api


urlpatterns = [
    path('msg_counts/', api.MsgCountView.as_view(), name='api_msg_counts'),
]