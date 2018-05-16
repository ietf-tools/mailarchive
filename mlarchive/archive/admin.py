from django.contrib import admin

from mlarchive.archive.models import Message, EmailList, Attachment, Thread


class MessageAdmin(admin.ModelAdmin):
    raw_id_fields = ('email_list', 'in_reply_to', 'thread')

class EmailListAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']

admin.site.register(Message, MessageAdmin)
admin.site.register(EmailList, EmailListAdmin)
admin.site.register(Attachment)
admin.site.register(Thread)
