#!/usr/bin/python
'''
This script checks all active private lists memberships, if membership has changed since
last time it was run, the list membership db table is updated.  This script can be run
periodically by cron.
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

from django.contrib.auth.models import User
from ietf.person.models import Email
from optparse import OptionParser
from mlarchive.archive.models import EmailList
import hashlib
import base64

try:
    from subprocess import check_output
except ImportError:
    from mlarchive.utils import check_output


def lookup(address):
    '''
    This function takes an email address and looks in Datatracker for an associated
    Datatracker account name.  Returns None if the email is not found or if there is no
    associated User account.
    '''
    try:
        email = Email.objects.using('ietf').get(address=address)
    except Email.DoesNotExist:
        return None

    try:
        username = email.person.user.username
    except AttributeError:
        return None

    return username

def process_members(mlist, emails):
    '''
    This function takes an EmailList object and a list of emails, from the mailman list_members
    command and creates the appropriate list membership relationships
    '''
    mlist.members.clear()
    for email in emails:
        name = lookup(email)
        if name:
            user, created = User.objects.get_or_create(username=name)
            mlist.members.add(user)

def main():
    usage = "usage: %prog"
    parser = OptionParser(usage=usage)
    parser.add_option("-q", "--quiet", help="don't print lists as they are processed",
                      action="store_true", default=False)
    (options, args) = parser.parse_args()

    cmd = os.path.join(settings.MAILMAN_DIR,'bin/list_members')

    for mlist in EmailList.objects.filter(private=True,active=True):
        if not options.quiet:
            print "Processing: %s" % mlist.name

        output = check_output([cmd,mlist.name])
        sha = hashlib.sha1(output)
        digest = base64.urlsafe_b64encode(sha.digest())
        if mlist.members_digest != digest:
            process_members(mlist,output.split())
        mlist.members_digest = digest
        mlist.save()

if __name__ == "__main__":
    main()