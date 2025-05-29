from django.contrib import admin
from mlarchive.archive.models import (Message, EmailList, Attachment, Thread,
    Redirect, UserEmail, MailmanMember)


class MessageAdmin(admin.ModelAdmin):
    raw_id_fields = ('email_list', 'in_reply_to', 'thread')


class EmailListAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']


class UserEmailAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    search_fields = ['address']


class MailmanMemberAdmin(admin.ModelAdmin):
    search_fields = ['address']


admin.site.register(Message, MessageAdmin)
admin.site.register(EmailList, EmailListAdmin)
admin.site.register(Attachment)
admin.site.register(Thread)
admin.site.register(Redirect)
admin.site.register(UserEmail, UserEmailAdmin)
admin.site.register(MailmanMember, MailmanMemberAdmin)
