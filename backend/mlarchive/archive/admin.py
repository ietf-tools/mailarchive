from django.contrib import admin, messages
from rangefilter.filters import DateRangeQuickSelectListFilterBuilder

from mlarchive.archive.models import (Message, EmailList, Attachment, Thread,
    Redirect, UserEmail, MailmanMember, Subscriber, StoredObject, TaskLock, Watermark)
from mlarchive.archive.tasks import move_list_blobs_task
from mlarchive.archive.utils import move_list_blobs_lock_name


class MessageAdmin(admin.ModelAdmin):
    raw_id_fields = ('email_list', 'in_reply_to', 'thread')
    search_fields = ['msgid', 'hashcode', 'frm']
    search_help_text = 'Search by msgid, hashcode or from fields'


class EmailListAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']
    actions = ['move_message_blobs']

    @admin.action(permissions=['change'],
                  description='Move existing message blobs to match list visibility')
    def move_message_blobs(self, request, queryset):
        """Queue a move of each selected list's blobs into the bucket matching its visibility.

        Changing a list's visibility moves nothing, so its older messages stay in the
        old bucket until this is run. Each list's current visibility is passed along,
        and a move stops early if the list's visibility changes while it runs.
        """
        queued = 0
        for email_list in queryset:
            lock = TaskLock.objects.filter(name=move_list_blobs_lock_name(email_list.pk)).first()
            if lock:
                self.message_user(
                    request, f'A blob move for {email_list.name} has been running since '
                    f'{lock.created:%Y-%m-%d %H:%M} UTC, not queued', messages.WARNING)
                continue
            move_list_blobs_task.delay(list_id=email_list.pk, private=email_list.private)
            queued += 1
        if queued:
            self.message_user(request, f'Queued a blob move for {queued} list(s)', messages.SUCCESS)


class UserEmailAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    search_fields = ['address']


class MailmanMemberAdmin(admin.ModelAdmin):
    search_fields = ['address']


class StoredObjectAdmin(admin.ModelAdmin):
    list_display = ('store', 'name', 'modified', 'deleted')
    list_filter = [
        'store',
        ('modified', DateRangeQuickSelectListFilterBuilder()),
        ('deleted', DateRangeQuickSelectListFilterBuilder()),
    ]
    list_display_links = ['name']
    search_fields = ['name', 'sha384']
    search_help_text = 'Search by object name or sha384 digest'


admin.site.register(Message, MessageAdmin)
admin.site.register(EmailList, EmailListAdmin)
admin.site.register(Attachment)
admin.site.register(Thread)
admin.site.register(Redirect)
admin.site.register(Subscriber)
admin.site.register(UserEmail, UserEmailAdmin)
admin.site.register(MailmanMember, MailmanMemberAdmin)
admin.site.register(StoredObject, StoredObjectAdmin)
admin.site.register(TaskLock)
admin.site.register(Watermark)
