"""
Built-in, globally-available admin actions. (ala Django)
These take a request object and queryset of objects to act on.
"""

from django.contrib import messages
from django.shortcuts import redirect

def remove_selected(request, queryset):
    """Remove selected messages from the database and index.

    Haystack RealtimeSignalProcessor will remove the entries from the index.
    http://django-haystack.readthedocs.org/en/latest/signal_processors.html \
        #realtime-realtimesignalprocessor

    Our _message_remove receiver will handle moving the message file to the "removed"
    directory
    """
    count = queryset.count()
    queryset.delete()
    messages.success(request, '%d Message(s) Removed' % count)
    return redirect('archive_admin')

def not_spam(request, queryset):
    """Mark selected messages as not spam (spam_score=0)"""
    count = queryset.count()
    # queryset.update() doesn't call save() which means the index doesn't get updated
    # via RealtimeSingalProcessor, need to loop through and call save()
    for message in queryset:
        message.spam_score=0
        message.save()
    messages.success(request, '%d Message(s) Marked not Spam' % count)
    return redirect('archive_admin')