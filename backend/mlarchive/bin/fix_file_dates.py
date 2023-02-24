#!../../../env/bin/python
'''
Background: the current IETF mail archive was initially imported on April 18, 2014.
Message files imported at this time all have dates of ~ April 18. This is about
2 million message files, or half of the archive as of 2023. The ISODE IMAP service
uses message file dates for sorting. This script will go through all messages older
than May 10 2014, when the dust settled from imports, and set the file modified time
equal to the message time, based on the message headers.
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import datetime
import os

from mlarchive.archive.models import Message


def main():
    cutoff = datetime.datetime(2014, 5, 10)
    for message in Message.objects.filter(date__lt=cutoff):
        path = message.get_file_path()
        atime = mtime = message.date.timestamp()
        os.utime(path, times=(atime, mtime))


if __name__ == "__main__":
    main()
