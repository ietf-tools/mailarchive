#!/usr/bin/python
'''
This script scans the MHonArc web archive, and creates a record in Legacy for each message
(about 1.4 million as of 05-15-13).  This table in turn can be used by the initial import
to filter out messages that aren't in the web archives, as a way to leverage all the manual
work that was done purging spam from the web archives.  The Leagcy table will also be used
for redirecting requests to the old archive to the new one.
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

from mlarchive.archive.models import *
from email.utils import parseaddr
import HTMLParser
import glob
import mailbox
import os
import re
import warnings

def main():
    errors = 0
    count = 0
    noid = 0
    NOIDPATTERN = re.compile(r'.*@NO-ID-FOUND.mhonarc.com')
    PATTERN = re.compile(r'<!--X-Message-Id:\s+(.*)\s+-->')
    dirs = glob.glob('/a/www/ietf-mail-archive/web*/*/current/')
    #dirs = glob.glob('/a/www/ietf-mail-archive/web/pwe3/current/')
    html_parser = HTMLParser.HTMLParser()
    for dir in sorted(dirs):
        listname = dir.split('/')[-3]
        print "Importing %s" % listname
        for fil in glob.glob(dir + 'msg?????.html'):
            count += 1
            with open(fil) as f:
                found = False
                for line in f:
                    if line.startswith('<!--X-Message-Id:'):
                        match = PATTERN.match(line)
                        if match:
                            found = True
                            msgid = match.groups()[0]
                            # in msgNNNNN.html message-id's are escaped, need to unescape
                            msgid = html_parser.unescape(msgid)
                            if re.match(NOIDPATTERN,msgid):
                                noid += 1
                        else:
                            raise Error('pattern failed (%s)' % fil)
                        break

                try:
                    if found:
                        u = unicode(msgid) # test for unknown encodings
                        number = int(os.path.basename(fil)[3:8])
                        Legacy.objects.create(msgid=msgid,email_list_id=listname,number=number)
                    else:
                        raise Exception("No Message Id: %s" % fil)
                except Exception as error:
                    print "Import Error [{0}, {1}]".format(fil,error.args)
                    errors += 1
    print "Errors: %d" % errors
    print "Files: %d" % count
    print "NO IDs: %d" % noid

if __name__ == "__main__":
    # debug version: treat warnings as errors
    #with warnings.catch_warnings(record=True) as w:
    #    # Cause all warnings to always be triggered.
    #    warnings.simplefilter("error")
    #    main()
    main()
