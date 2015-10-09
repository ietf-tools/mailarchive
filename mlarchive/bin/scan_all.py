#!/usr/bin/python
"""
Generic scan script.  Define a scan as a function.  Specifiy the function as the
first command line argument.

usage:

scan_all.py [func name] [optional arguments][

"""
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.development'
django.setup()

# -------------------------------------------------------------------------------------

from mlarchive.archive.models import *
from mlarchive.bin.scan_utils import *
from mlarchive.archive.management.commands import _classes
from tzparse import tzparse
from pprint import pprint
from pytz import timezone

import argparse
import datetime
import email
import glob
import mailbox
import re
import sys

date_pattern = re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
dupetz_pattern = re.compile(r'[\-\+]\d{4} \([A-Z]+\)$')

date_formats = ["%a %b %d %H:%M:%S %Y",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%a %b %d %H:%M:%S %Y %Z"]

mlists = ['abfab','alto','aqm','codec','dane','dmarc','dmm','dnsop',
    'dns-privacy','endymail','gen-art','grow','hipsec','homenet',
    'i2rs','ipsec','jose','l3vpn','lisp','lwip','mif','multimob',
    'nvo3','oauth','opsawg','opsec','ospf','p2psip','paws','pce',
    'perpass','precis','rtgwg','sidr','softwires','spring','sshmgmt',
    'taps','trans','uta','websec']
# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def convert_date(date):
    """Try different patterns to convert string to naive UTC datetime object"""
    for format in date_formats:
        try:
            result = tzparse(date.rstrip(),format)
            if result:
                # convert to UTC and make naive
                utc_tz = timezone('utc')
                time = utc_tz.normalize(result.astimezone(utc_tz))
                time = time.replace(tzinfo=None)                # make naive
                return time
        except ValueError:
            pass

def get_date_part(str):
    """Get the date portion of the envelope header.  Based on the observation
    that all date parts start with abbreviated weekday
    """
    match = date_pattern.search(str)
    if match:
        date = match.group()

        # a very few dates have redundant timezone designations on the end
        # which tzparse can't handle.  If this is the case strip it off
        # ie. Wed, 6 Jul 2005 12:24:15 +0100 (BST)
        if dupetz_pattern.search(date):
            date = re.sub(r'\s\([A-Z]+\)$','',date)
        return date
    else:
        return None

def is_ascii(s):
    if s == None:
        return True
    try:
        s.decode('ascii')
    except UnicodeDecodeError:
        return False
    return True


# ---------------------------------------------------------
# Scan Functions
# ---------------------------------------------------------

def bodies():
    """Call get_body_html() and get_body() for every message in db. Use logging in
    generator_handler methods to gather stats.
    """
    query = Message.objects.all()
    total = Message.objects.count()
    for msg in query:
        try:
            x = msg.get_body_html()
            y = msg.get_body()
        except (UnicodeDecodeError, LookupError, TypeError) as e:
            print '{0} [{1}]'.format(e, msg.pk)
        if msg.pk % 1000 == 0:
            print 'processed {0} of {1}'.format(msg.pk,total)

def count(listname):
    """Count number of messages in legacy archive for listname"""
    total = 0
    years = {}
    for mb in get_mboxs(listname):
        parts = mb._file.name.split('/')
        num = len(mb)
        year = parts[-1][:4]
        years[year] = years.get(year,0) + num
        print "%s/%s: %d" % (parts[-2],parts[-1],num)
        total += num
    print "Total: %d" % total
    pprint(years)

def date(start):
    """Calls get_date for every message in (old) archive.  Use 'start' argument
    to offset beginning of run"""
    listname = ''
    processing = False
    total = 0
    for path in all_mboxs():
        name = os.path.basename(os.path.dirname(path))
        if start == name or processing == True:
            processing = True
        else:
            continue

        if name != listname:
            listname = name
            print listname
        try:
            mb = _classes.get_mb(path)
        except _classes.UnknownFormat:
            print "Unknown format: %s" % path
            continue

        for i,msg in enumerate(mb):
            total += 1
            try:
                mw = _classes.MessageWrapper(msg,listname)
                date = mw.get_date()
            except _classes.NoHeaders as error:
                print "Error: %s,%d (%s)" % (path, i, error.args)

    print "Total: %s" % total

def header_date():
    nf = 0
    count = 0
    with open('received.log') as f:
        paths = f.read().splitlines()
    for path in paths:
        mb = _classes.get_mb(path)
        for i,msg in enumerate(mb):
            count += 1
            date = msg.get('date')
            if not date:
                date = msg.get('sent')

            if not date:
                print "Date not found: %s,%s" % (path,i)
                nf += 1
                #sys.exit(1)
                continue

            result = _classes.parsedate_to_datetime(date)
            if not result:
                print "Parse Error: %s" % date
                #sys.exit(1)
    print "Count: %s\nNot Found: %s" % (count,nf)

def envelope_date():
    """Quickly test envelope date parsing on every standard mbox file in archive"""
    #for path in ['/a/www/ietf-mail-archive/text/lemonade/2002-09.mail']:
    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if line.startswith('From '):
                date = get_date_part(line.rstrip())
                if date == None:
                    print path,line
                if not convert_date(date.rstrip()):
                    print path,date

def envelope_regex():
    """Quickly test envelope regex matching on every standard mbox file in archive"""
    #for path in ['/a/www/ietf-mail-archive/text/lemonade/2002-09.mail']:
    # pattern = re.compile(r'From (.*@.* |MAILER-DAEMON ).{24}')
    pattern = re.compile(r'From .* (Sun|Mon|Tue|Wed|Thu|Fri|Sat)( |,)')

    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if line.startswith('From '):
                if not pattern.match(line):
                    print path,line

def html_only():
    """Scan all mboxs and report messages that have only one MIME part that is text/html"""
    elist = ''
    for path in all_mboxs():
        name = os.path.basename(os.path.dirname(path))
        if elist != name:
            elist = name
            print "Scanning %s" % name
        if name in ('django-project','iab','ietf'):
            continue
        mb = _classes.get_mb(path)
        for msg in mb:
            if msg.is_multipart() == False:
                if msg.get_content_type() == 'text/html':
                    print msg['message-id']

def lookups():
    """Test the message find routines"""
    from haystack.query import SearchQuerySet
    from mlarchive.archive.view_funcs import find_message_date, find_message_date_reverse, find_message_gbt

    for elist in EmailList.objects.all():
        print "Checking list: {}".format(elist.name)
        sqs = SearchQuerySet().filter(email_list=elist.pk).order_by('date')
        print "-date"
        for m in sqs:
            if find_message_date(sqs,m.object) == -1:
                print "Problem with {}:{}".format(elist.name,m.object.msgid)
        sqs = SearchQuerySet().filter(email_list=elist.pk).order_by('-date')
        print "-date-reverse"
        for m in sqs:
            if find_message_date_reverse(sqs,m.object) == -1:
                print "Problem with {}:{}".format(elist.name,m.object.msgid)
        sqs = SearchQuerySet().filter(email_list=elist.pk).order_by('tdate','date')
        print "-gbt"
        for m in sqs:
            if find_message_gbt(sqs,m.object) == -1:
                print "Problem with {}:{}".format(elist.name,m.object.msgid)

def mailbox_types():
    """Scan all mailbox files and print example of each unique envelope form other
    than typical mbox or mmdf
    """
    matches = dict.fromkeys(_classes.SEPARATOR_PATTERNS)
    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if not (line.startswith('From ') or line.startswith('\x01\x01\x01\x01')):
                for pattern in _classes.SEPARATOR_PATTERNS:
                    if pattern.match(line):
                        if not matches[pattern]:
                            matches[pattern] = path
                            print "%s: %s" % (pattern.pattern, path)
                        break

def missing_files():
    """Scan messages in date range and report if any are missing the archive file"""
    total = 0
    start = datetime.datetime(2014,01,20)
    end = datetime.datetime(2014,01,23)
    messages = Message.objects.filter(date__gte=start,date__lte=end)
    for message in messages:
        if not os.path.exists(message.get_file_path()):
            print 'missing: %s:%s:%s' % (message.email_list, message.pk, message.date)
            total += 1
            #message.delete()
    print '%d of %d missing.' % (total, messages.count())

def mmdfs():
    """Scan all mailbox files and print first lines of MMDF types, looking for
    different styles
    """
    #import binascii
    count = 0
    for path in all_mboxs():
        try:
            mb = _classes.get_mb(path)
        except _classes.UnknownFormat:
            pass
        if isinstance(mb,_classes.CustomMMDF):
            with open(path) as f:
                if f.read(10) == '\x01\x01\x01\x01\n\x01\x01\x01\x01\n':
                    print "%s" % path
                    count += 1
    print "Total: %s" % count

def message_rfc822():
    """Scan all lists for message/rfc822"""
    for elist in EmailList.objects.all().order_by('name'):
        print "Scanning {}".format(elist.name)

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())
            count = 0
            for part in message.walk():
                if part.get_content_type() == 'message/rfc822':
                    count += 1
                    payload = part.get_payload()
                    if len(payload) != 1 or payload[0].get_content_type() != 'text/plain':
                        print msg.pk,payload,' '.join([ x.get_content_type() for x in payload])

            if count > 1:
                print "{}:{}".format(msg.pk,count)

def multipart():
    """Scan all lists, accumulate types which are multipart"""
    types = {}
    for elist in EmailList.objects.all().order_by('name'):
        print "Scanning {}".format(elist.name)

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())
            for part in message.walk():
                if part.is_multipart():
                    types[part.get_content_type()] = types.get(part.get_content_type(),0) + 1

    print types

def received_date(start):
    """Test receive date parsing.  Start at list named by 'start', use 80companions
    to run in full
    """
    listname = ''
    processing = False
    norecs = 0
    nrmap = {}
    total = 0
    aware = 0
    for path in all_mboxs():
        name = os.path.basename(os.path.dirname(path))
        if start == name or processing == True:
            processing = True
        else:
            continue

        if name != listname:
            listname = name
            print listname
        try:
            mb = _classes.get_mb(path)
        except _classes.UnknownFormat:
            print "Unknown format: %s" % path
            continue

        for i,msg in enumerate(mb):
            total += 1
            recs = msg.get_all('received')
            if not recs:
                norecs += 1
                print "no received header:%s,%s" % (path,i)
                nrmap[path] = nrmap.get(path,0) + 1
                continue
            parts = recs[0].split(';')
            try:
                # take the final bit (almost always 2, but sometimes ";" appears earlier
                date =  _classes.parsedate_to_datetime(parts[-1])
            except IndexError as error:
                print "Failed: %s:%s (%s)" % (path,i,error)
                sys.exit(1)
            if not date:
                print "Total: %s\nnorecs: %s" % (total,norecs)
                print "Failed: %s:%s:%s" % (path,i,recs)
                sys.exit(1)
            elif _classes.is_aware(date):
                aware += 1
    print "Total: %s\nnorecs: %s\naware: %s" % (total,norecs,aware)
    with open('received.log','w') as f:
        for key in nrmap:
            f.write(key + '\n')

def subjects(listname):
    """Return subject line of all messages for listname"""
    for msg in process([listname]):
        print "%s: %s" % (msg.get('date'),msg.get('subject'))

def run_messagewrapper_process():
    """Call MessageWrapper.process() for each message in the (old) archive, to check
    for errors after changing some underlying code"""
    for msg in all_messages(['ancp']):
        '''follow date() pattern, need to know list, etc, during iteration'''
        pass

def unicode():
    """Scan all lists looking for non-ascii data in headers to test handling"""
    for elist in EmailList.objects.all().order_by('name'):
    # for elist in EmailList.objects.filter(name='homenet').order_by('name'):
        print "Scanning {}".format(elist.name)

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())

            for header in ('from','subject'):
                if not is_ascii(message[header]):
                    print "Message: {},   {}:{}".format(msg.pk,header,message[header])
                    return


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Run an archive scan.')
    parser.add_argument('function')
    parser.add_argument('extras', nargs='*')
    args = vars(parser.parse_args())
    if args['function'] in globals():
        func = globals()[args['function']]
        func(*args['extras'])
    else:
        raise argparse.ArgumentTypeError('no scan function: %s' % args['function'])

if __name__ == "__main__":
    main()
