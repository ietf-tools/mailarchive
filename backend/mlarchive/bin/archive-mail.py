#!../../../env/bin/python
'''
This is the Mailman External Archive interface for the Email Archive.  It takes an email message
on standard input and saves the message in the archive.  The message listname is required as the
first argument.  Use --public to specifiy a public list or --private to specify a private list.
The default is public.
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import sys
from optparse import OptionParser

from mlarchive.archive.mail import archive_message

import logging
logger = logging.getLogger('mlarchive.bin.archive-mail')


def main():
    logger.info('called with arguments: %s' % sys.argv)
    usage = "usage: %prog LISTNAME [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("--public", help="archive message to public archive (default)",
                      action="store_true", dest='public', default=False)
    parser.add_option("--private", help="archive message to private archive",
                      action="store_true", dest='private', default=False)
    (options, args) = parser.parse_args()

    try:
        listname = sys.argv[1]
    except IndexError:
        sys.exit("%s: missing listname\nTry `%s --help for more information" %
                 (sys.argv[0],sys.argv[0]))

    if options.public and options.private:
        sys.exit("%s: invalid arguments\nTry `%s --help for more information" %
                 (sys.argv[0],sys.argv[0]))

    data = sys.stdin.buffer.read()
    logger.info('envelope: %s' % data.decode('utf8', errors='ignore').split('\n', 1)[0])
    status = archive_message(data,listname,private=options.private)

    logger.info('archive_message exit status: %s' % status)
    sys.exit(status)

if __name__ == "__main__":
    main()
