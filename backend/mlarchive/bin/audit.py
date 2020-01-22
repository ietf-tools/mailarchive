#!../../../env/bin/python


'''
Script to check for missing message files in the archive

'''

# Standalone broilerplate -------------------------------------------------------------
from .django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------
import glob
import sys
import os
import subprocess

from django.conf import settings
from mlarchive.archive.models import Message, EmailList


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


lists = EmailList.objects.all().order_by('name')
lists = EmailList.objects.filter(name='dmarc-report')
missing = []

for elist in lists:
    path = os.path.join(settings.ARCHIVE_DIR, elist.name)
    if not os.path.isdir(path):
        continue
    files = os.listdir(path)
    messages = Message.objects.filter(email_list__name=elist.name)
    eprint("{}:{}:{}".format(elist.name,len(files),messages.count()))
    if len(files) != messages.count():
        #print()
        #sys.exit()
        for message in messages:
            if os.path.basename(message.get_file_path()) not in files:
                missing.append(message)
                print("%s:%s" % (elist.name, message.msgid))

for message in missing:
    pattern = "^Message-Id: {}".format(message.msgid)
    if message.email_list.private:
        path = os.path.join('/a/www/ietf-mail-archive/text-secure', message.email_list.name)
    else:
        path = os.path.join('/a/www/ietf-mail-archive/text', message.email_list.name)
    if not os.path.isdir(path):
        continue
    files = glob.glob(path + '/*.mail')
    files.sort(key=os.path.getmtime, reverse=True)
    output = ''
    for file in files:
        try:
            output = subprocess.check_output(['grep', '-l', "'{}'".format(pattern), file])
            #print("grepping {} from {} output {}".format(pattern,file,output))
        except Exception as e:
            #print(e, e.output, e.cmd)
            continue
        if output:
            break

    print("{}:{}".format(message.get_file_path(), output))
