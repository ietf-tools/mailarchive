"""
Built-in, globally-available admin actions. (ala Django)
These take a request object and queryset of objects to act on.
"""
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect

from mlarchive.archive.tasks import remove_selected_task, mark_not_spam_task

import logging
logger = logging.getLogger(__name__)


def is_ajax(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        return True
    else:
        return False


def remove_selected(request, queryset):
    """Remove selected messages from the database and index.

    CelerySignalProcessor will remove the entries from the index.

    Our _message_remove receiver will handle moving the message file to the "removed"
    directory
    """
    queryset.update(spam_score=settings.SPAM_SCORE_TO_REMOVE)
    transaction.on_commit(
        lambda: remove_selected_task.delay(user_id=request.user.id)
    )

    if is_ajax(request):
        return JsonResponse({
            'status': 'success',
            'message': f'{queryset.count()} Message(s) queued for removal.',
        })
    else:
        messages.success(request, f'{queryset.count()} Message(s) queued for removal')
        return redirect('archive_admin')


def not_spam(request, queryset):
    """Mark selected messages as not spam (spam_score=settings.SPAM_SCORE_NOT_SPAM)"""
    mark_not_spam_task.delay(message_ids=[q.id for q in queryset])

    if is_ajax(request):
        return JsonResponse({
            'status': 'success',
            'message': f'{queryset.count()} Message(s) queued for marking not spam.',
        })
    else:
        messages.success(request, f'{queryset.count()} Message(s) queued for marking not Spam')
        return redirect('archive_admin')
