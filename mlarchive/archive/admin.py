from django.contrib import admin

from mlarchive.archive.models import *

admin.site.register(Message)
admin.site.register(EmailList)
admin.site.register(Attachment)
admin.site.register(Thread)