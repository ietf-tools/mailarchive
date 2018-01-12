"""
Built-in, globally-available admin actions. (ala Django)
These take a request object and queryset of objects to act on.
"""

from django.contrib import messages
from django.shortcuts import redirect

import logging
logger = logging.getLogger('mlarchive.custom')


def is_ajax(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        return True
    else:
        return False


def remove_selected(request, queryset):
    """Remove selected messages from the database and index.

    Haystack RealtimeSignalProcessor will remove the entries from the index.
    http://django-haystack.readthedocs.org/en/latest/signal_processors.html \
        #realtime-realtimesignalprocessor

    Our _message_remove receiver will handle moving the message file to the "removed"
    directory
    """
    count = queryset.count()
    for message in queryset:
        logger.info('User %s removed message [list=%s,hash=%s,msgid=%s,pk=%s]' %
                (request.user, message.email_list, message.hashcode, message.msgid,
                message.pk))
    queryset.delete()
    if not is_ajax(request):
        messages.success(request, '%d Message(s) Removed' % count)
        return redirect('archive_admin')


def not_spam(request, queryset):
    """Mark selected messages as not spam (spam_score=0)"""
    count = queryset.count()
    # queryset.update() doesn't call save() which means the index doesn't get updated
    # via RealtimeSingalProcessor, need to loop through and call save()
    for message in queryset:
        message.spam_score = -1
        message.save()
    if not is_ajax(request):
        messages.success(request, '%d Message(s) Marked not Spam' % count)
        return redirect('archive_admin')
