#!/usr/bin/python
'''
This script will recreate attachments for specified messages
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import email
from mlarchive.archive.models import Message
from mlarchive.archive.management.commands import _classes

pks = [2108476,1210205,1210328,1300179,1440463,2108877,1517225,2108475]

for pk in pks:
    message = Message.objects.get(pk=pk)
    with open(message.get_file_path()) as f:
        msg = email.message_from_file(f)
    mw = _classes.MessageWrapper(msg,message.email_list.name)
    mw._archive_message = message
    message.attachment_set.all().delete()
    mw.process_attachments()
    print "MSG {}: {}".format(pk, message.attachment_set.all())

