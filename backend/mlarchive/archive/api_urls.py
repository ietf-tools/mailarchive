from django.urls import path

from mlarchive.archive import api


urlpatterns = [
    path('v1/stats/msg_counts/', api.MsgCountView.as_view(), name='api_msg_counts'),
    path('v1/stats/subscriber_counts/', api.SubscriberCountsView.as_view(), name='api_subscriber_counts'),
    path('v1/message/<list_type>/<list_name>/', api.ImportMessageView.as_view(), name='api_import_message'),
]
