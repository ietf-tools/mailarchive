#!/usr/bin/python
"""
Utilities for running scans on mailbox files
"""

import glob
import mailbox
import os
import re

from mlarchive.archive.management.commands import _classes

#FILE_PATTERN = re.compile(r'\d{4}-\d{2}.mail$')
FILE_PATTERN = re.compile(r'^\d{4}-\d{2}(|.mail)$')

def is_mbox(filename):
    basename = os.path.basename(filename)
    if not FILE_PATTERN.match(basename):
        return False
    if os.path.isdir(filename):
        return False
    statinfo = os.stat(filename)
    if statinfo.st_size == 0:
        return False
    return True

def get_mboxs(listname):
    """Returns mbox objects for listname"""
    all = sorted(glob.glob('/a/www/ietf-mail-archive/text/%s/*' % listname))
    files = filter(is_mbox, all)
    for fil in files:
        mb = _classes.get_mb(fil)
        yield mb

def process(names):
    """This is a utility function which takes a list of email list names and returns
    Message objects
    """
    for name in names:
        all = sorted(glob.glob('/a/www/ietf-mail-archive/text/%s/*' % name))
        files = filter(is_mbox, all)
        for fil in files:
            #mb = mailbox.mbox(fil)
            mb = _classes.get_mb(fil)
            for msg in mb:
                yield msg
            mb.close()

def all_mboxs():
    """Generator that returns the full path of all non-empty mbox files in the archive.
    """
    dirs = sorted(glob.glob('/a/www/ietf-mail-archive/text*/*'))
    for dir in dirs:
        all = [ os.path.join(dir,f) for f in os.listdir(dir) ]
        files = filter(is_mbox, all)
        for file in files:
            size = os.stat(file).st_size
            if size != 0:
                yield file