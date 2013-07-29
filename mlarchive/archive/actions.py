"""
Built-in, globally-available admin actions. (ala Django)
"""

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse

def delete_selected(request, queryset):
    '''
    Delete selected messages
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
    # update() on querysets doesn't call save signals, need to loop through and call save()
    #queryset.update(spam_score=0)
    for message in queryset:
        message.spam_score=0
        message.save()
    messages.success(request, '%d Messages Marked not Spam' % count)
    url = reverse('archive_admin')
    return HttpResponseRedirect(url)