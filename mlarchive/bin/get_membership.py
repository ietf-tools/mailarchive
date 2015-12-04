#!/usr/bin/python
'''
This script checks all active private lists memberships, if membership has changed since
last time it was run, the list membership db table is updated.  This script can be run
periodically by cron.
'''
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
sys.path.insert(0, '/a/www/ietf-datatracker/web')
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.production'
django.setup()

# -------------------------------------------------------------------------------------
from django.db.models.signals import post_save
from django.conf import settings
from django.contrib.auth.models import User
from ietf.person.models import Email
from optparse import OptionParser
from mlarchive.archive.models import EmailList, _list_save_handler, _export_lists
from subprocess import CalledProcessError
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

    # TODO: use Django 1.5 Custom User to support username max_length = 64
    return username[:30]

def process_members(mlist, emails):
    '''
    This function takes an EmailList object and a list of emails, from the mailman list_members
    command and creates the appropriate list membership relationships
    '''
    members = mlist.members.all()
    for email in emails:
        name = lookup(email)
        if name:
            user, created = User.objects.get_or_create(username=name)
            if user not in members:
                mlist.members.add(user)

def main():
    usage = "usage: %prog"
    parser = OptionParser(usage=usage)
    parser.add_option("-q", "--quiet", help="don't print lists as they are processed",
                      action="store_true", default=False)
    (options, args) = parser.parse_args()

    list_members_cmd = os.path.join(settings.MAILMAN_DIR,'bin/list_members')
    list_lists_cmd = os.path.join(settings.MAILMAN_DIR,'bin/list_lists')
    
    # disconnect the EmailList post_save signal, we don't want to call it multiple
    # times if many lists memberships have changed
    post_save.disconnect(_list_save_handler,sender=EmailList)
    has_changed = False
    
    known_lists = check_output([list_lists_cmd]).split()
    assert len(known_lists) > 100       # assert reasonable output
    
    for mlist in EmailList.objects.filter(private=True,active=True):
        # skip lists that aren't managed by mailman
        if mlist.name not in known_lists:
            continue
        
        if not options.quiet:
            print "Processing: %s" % mlist.name
            
        try:
            output = check_output([list_members_cmd,mlist.name])
        except CalledProcessError:
            # some lists don't exist in mailman
            continue
            
        sha = hashlib.sha1(output)
        digest = base64.urlsafe_b64encode(sha.digest())
        if mlist.members_digest != digest:
            has_changed = True
            process_members(mlist,output.split())
            mlist.members_digest = digest
            mlist.save()

    if has_changed:
        _export_lists()

if __name__ == "__main__":
    main()
