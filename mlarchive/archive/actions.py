"""
Built-in, globally-available admin actions. (ala Django)
These take a request object and queryset of objects to act on.
"""

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse

def remove_selected(request, queryset):
    '''
    Remove selected messages from the database and index.

    Haystack RealtimeSignalProcessor will remove the entries from the index.
    http://django-haystack.readthedocs.org/en/latest/signal_processors.html#realtime-realtimesignalprocessor

    Our _message_remove receiver will handle moving the message file to the "removed" directory
    '''
    count = queryset.count()
    queryset.delete()
    messages.success(request, '%d Messages Deleted' % count)
    url = reverse('archive_admin')
    return HttpResponseRedirect(url)

def not_spam(request, queryset):
    '''
    Mark selected messages as not spam (spam_score=0)
    '''
    count = queryset.count()
    # update() on querysets doesn't call save() which means the index doesn't get updated
    # via RealtimeSingalProcessor, need to loop through and call save()
    # queryset.update(spam_score=0)
    for message in queryset:
        message.spam_score=0
        message.save()
    messages.success(request, '%d Messages Marked not Spam' % count)
    url = reverse('archive_admin')
    return HttpResponseRedirect(url)