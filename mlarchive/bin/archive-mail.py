#!/usr/bin/python
'''
This is the Mailman External Archive interface for the Email Archive.  It takes an email message
on standard input and saves the message in the archive.  The message listname is required as the
first argument.  Use --public to specifiy a public list or --private to specify a private list.
The default is public.
'''
# standalone script ---------------------------------------
import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(BASE_DIR + "/../.."))

from django.core.management import setup_environ
from mlarchive import settings
setup_environ(settings)
# ---------------------------------------------------------

import email
from optparse import OptionParser
import mlarchive.archive.management.commands._classes as _classes

def main():
    usage = "usage: %prog LISTNAME [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-public", help="archive message to public archive (default)",
                      action="store_true", dest='public', default=False)
    parser.add_option("-private", help="archive message to private archive",
                      action="store_true", dest='private', default=False)
    (options, args) = parser.parse_args()

    # TODO should we use EX_TEMPFAIL?
    try:
        listname = sys.argv[1]
    except IndexError:
        sys.exit("%s: missing listname\nTry `%s --help for more information" %
                 (sys.argv[0],sys.argv[0]))

    if options.public and options.private:
        sys.exit("%s: invalid arguments\nTry `%s --help for more information" %
                 (sys.argv[0],sys.argv[0]))

    msg = email.message_as_string(sys.stdin.read())
    _classes.archive_message(msg,listname,private=options.private)

if __name__ == "__main__":
    main()
