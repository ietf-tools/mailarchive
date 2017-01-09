from django.contrib import admin

from mlarchive.archive.models import *

class MessageAdmin(admin.ModelAdmin):
    raw_id_fields = ('email_list','in_reply_to','thread')


admin.site.register(Message, MessageAdmin)
admin.site.register(EmailList)
admin.site.register(Attachment)
admin.site.register(Thread)