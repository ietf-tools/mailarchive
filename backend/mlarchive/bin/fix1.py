#!../../../env/bin/python
'''
Fix uuid named files
'''

# Standalone broilerplate -------------------------------------------------------------
from .django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

from mlarchive.archive.models import Message
from email.utils import parseaddr
import glob
import email
import mailbox
import re
import os
import shutil

def main():
    files = glob.glob('/a/mailarch/data/archive/*/????????-????-????-????-????????????')
    print("{} files found".format(len(files)))

    for file in files:
        with open(file) as fp:
            msg = email.message_from_file(fp)
        filename = os.path.basename(file)
        listname = os.path.basename(os.path.dirname(file))
        msgid = msg['message-id'].strip('<>')
        message = Message.objects.get(email_list__name=listname,msgid=msgid)
        print("{}:{}".format(listname,msgid))
        print("{}  ==>  {}".format(file,message.hashcode))
        target = os.path.join(os.path.dirname(file),message.hashcode)
        shutil.move(file,target)

if __name__ == "__main__":
    main()
