#!../../../env/bin/python

# from __future__ import print_function
"""
Generic scan script to scan the archive for messages with particular attributes.
Define a scan as a function.  Specifiy the function as the first command line argument.
You can pass additional positional arguments on the command line, and specify them
in the function definition.

usage:

scan_all.py [func name] [optional arguments]

examples:
./scan_all.py find_mime text/x-perl-script

"""
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import datetime
import email
import os
import re
import sys
import time
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
# from tzparse import tzparse
from pprint import pprint
from pytz import timezone

from django.core.cache import cache
from django.db.models import Count
from haystack.query import SearchQuerySet

from mlarchive.archive.models import *
from mlarchive.bin.scan_utils import *
from mlarchive.archive.management.commands import _classes
from mlarchive.utils.encoding import decode_rfc2047_header, is_attachment
from mlarchive.archive.management.commands._classes import MessageWrapper, lookup_extension
from mlarchive.archive.management.commands._mimetypes import CONTENT_TYPES


print("DJANGO_SETTINGS_MODULE={}".format(os.environ['DJANGO_SETTINGS_MODULE']))

date_pattern = re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
dupetz_pattern = re.compile(r'[\-\+]\d{4} \([A-Z]+\)$')
from_line_re = re.compile(r'From .* (Sun|Mon|Tue|Wed|Thu|Fri|Sat)( |,)')

MAX_TERM_LENGTH = 245

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

def archived_at():
    """Find messages whose Archived-At header does not match url"""
    from email.parser import Parser
    parser = Parser()
    count = 0
    start = datetime.datetime(2014,1,1)
    messages = Message.objects.filter(date__gte=start)
    print('Processing: {}'.format(messages.count()))
    for n, message in enumerate(messages):
        if n % 10000 == 0:
            print('Processed: {} ({})'.format(n, count))
        msg = parser.parsestr(message.get_body_raw(), headersonly=True)
        if msg['archived-at'] and 'mailarchive' in msg['archived-at']:
            if message.hashcode.strip('=') not in msg['archived-at']:
                count = count + 1
                print(message.pk, message.hashcode, msg['archived-at'])
    
    print('Total checked: {}'.format(count))
        
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
            print('{0} [{1}]'.format(e, msg.pk))
        if msg.pk % 1000 == 0:
            print('processed {0} of {1}'.format(msg.pk,total))

def bogus_date():
    """Identify messages with no or incorrect date header.  Scans messages in new
    archive.  Checks header in message file, not the database, since we want to identify
    problem messages visible in IMAP"""
    no_date = 0
    bogus_date = 0
    total = Message.objects.count()
    min_date = datetime.datetime(1982,1,1)
    max_date = datetime.datetime.today() + datetime.timedelta(days=1)
    for message in Message.objects.iterator():
        with open(message.get_file_path()) as fp:
            msg = email.message_from_file(fp)
        if 'date' not in msg:
            no_date = no_date + 1
            print("Missing date header: {}:{}".format(message.email_list.name,message.pk))
            continue

        date = msg.get('date')
        dt = _classes.parsedate_to_datetime(date)
        dt = dt.replace(tzinfo=None)                # force naive
        if dt < min_date or dt > max_date:
            bogus_date = bogus_date + 1
            print("Bogus date: {}:{}, {}".format(message.email_list.name,message.pk,date))
        
        if message.pk % 1000 == 0:
            print('processed {0} of {1}'.format(message.pk,total))

    print("No Date:{}".format(no_date))
    print("Bogus Date: {}".format(bogus_date))

def bogus_mmdf():
    """Identify mbox files that start out with MMDF header ^A^A^A^A then proceed with
    normal "From " line separators."""
    total = 0
    for path in all_mboxs():
        with open(path) as f:
            line1 = f.readline()
            line2 = f.readline()
            if line1 == '\x01\x01\x01\x01\n' and from_line_re.match(line2):
                print(path)

    print("Total: %d" % total)

def count(listname):
    """Count number of messages in legacy archive for listname"""
    total = 0
    years = {}
    for mb in get_mboxs(listname):
        parts = mb._file.name.split('/')
        num = len(mb)
        year = parts[-1][:4]
        years[year] = years.get(year,0) + num
        print("%s/%s: %d" % (parts[-2],parts[-1],num))
        total += num
    print("Total: %d" % total)
    pprint(years)

def check_thread_first(fix=False):
    """Check for threads that don't have 'first' message.

    Example: ./scan_all.py --fix check_thread_first
    """
    threads = Thread.objects.filter(first__isnull=True)
    print("Threads without first message: {}".format(threads.count()))
    empty = 0
    for thread in threads:
        if thread.message_set.count() == 0:
            empty += 1
            if fix:
                thread.delete()
        else:
            if fix:
                first = thread.message_set.order_by('date').first()
                thread.first = first
                thread.save()
    print("{} empty threads".format(empty))
    if fix:
        threads = Thread.objects.filter(first__isnull=True)
        print("{} remaining threads without first message".format(threads.count()))

def check_thread_order(start,fix=False):
    """Compare message.thread_order in DB with index.  If fix==True save
    the database object, causing the index to get updated to match DB.
    
    Example: ./scan_all.py --fix check_thread_order 2017-01-15T00:00:00
    """
    print("start: {}    fix: {}".format(start,fix))
    start_date = parse(start)
    threads = Thread.objects.filter(date__gte=start_date)
    print("Checking {} threads.".format(threads.count()))
    total = 0
    for thread in threads:
        sqs = SearchQuerySet().filter(tid=thread.id).order_by('torder')
        for result in sqs:
            if result.torder != result.object.thread_order:
                if fix:
                    # compute_thread(thread)
                    result.object.save()
                    continue
                else:
                    total += 1
                    print("Mismatch: pk={} index_order={} db_order={}".format(result.object.pk,result.torder,result.object.thread_order))
    print("Total: {}".format(total))


def check_spam(elist):
    """Proceeding through the archive starting from most recent find spam, messages with
    X-Spam-Level: ***** or more
    """
    messages = Message.objects.filter(date__year__gte=1990).order_by('-date')
    if elist:
        messages = messages.filter(email_list__name=elist)
    for message in messages:
        path = message.get_file_path()
        with open(path) as file:
            msg = email.message_from_file(file)
        if msg['x-spam-level'] and msg['x-spam-level'].startswith('*****'):
            print(message.get_absolute_url(), message.date)


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
            print(listname)
        try:
            mb = _classes.get_mb(path)
        except _classes.UnknownFormat:
            print("Unknown format: %s" % path)
            continue

        for i,msg in enumerate(mb):
            total += 1
            try:
                mw = _classes.MessageWrapper(msg,listname)
                date = mw.get_date()
            except _classes.NoHeaders as error:
                print("Error: %s,%d (%s)" % (path, i, error.args))

    print("Total: %s" % total)

def find_mime(mime_type):
    """Searches the archive for specified MIME type, lowercase"""
    print("mime_type: {}".format(mime_type))
    for elist in EmailList.objects.all().order_by('name'):
        print("Scanning {}".format(elist.name))
        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())
            for part in message.walk():
                if part.get_content_type() == mime_type:
                    print("MSG:{}".format(msg.pk))

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
                print("Date not found: %s,%s" % (path,i))
                nf += 1
                #sys.exit(1)
                continue

            result = _classes.parsedate_to_datetime(date)
            if not result:
                print("Parse Error: %s" % date)
                #sys.exit(1)
    print("Count: %s\nNot Found: %s" % (count,nf))

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
                    print(path,line)
                if not convert_date(date.rstrip()):
                    print(path,date)

def envelope_regex():
    """Quickly test envelope regex matching on every standard mbox file in archive"""
    pattern = re.compile(r'From .* (Sun|Mon|Tue|Wed|Thu|Fri|Sat)( |,)')

    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if line.startswith('From '):
                if not pattern.match(line):
                    print(path,line)

def html_only():
    """Scan all mboxs and report messages that have only one MIME part that is text/html"""
    elist = ''
    for path in all_mboxs():
        name = os.path.basename(os.path.dirname(path))
        if elist != name:
            elist = name
            print("Scanning %s" % name)
        if name in ('django-project','iab','ietf'):
            continue
        mb = _classes.get_mb(path)
        for msg in mb:
            if msg.is_multipart() == False:
                if msg.get_content_type() == 'text/html':
                    print(msg['message-id'])

def incoming():
    """Check files in data/incoming to see if they exist in archive"""
    defects = 0
    missing = 0
    empty = 0
    path = '/a/mailarch/data/incoming'
    files = os.listdir(path)
    for file in  files:
        # print(file)
        full = os.path.join(path, file)
        if not os.path.isfile(full):
            continue
        if os.path.getsize(full) == 0:
            empty = empty + 1
            print('{}:0'.format(file))
            continue
        with open(full, 'rb') as f:
            msg = email.message_from_binary_file(f)
        if msg['defects']:
            defects = defects + 1
            print('{}:{}'.format(file, msg['defects']))
            continue
        msgid = msg['message-id'].strip('<>')
        elist = file.split('.')[0]
        if Message.objects.filter(email_list__name=elist, msgid=msgid).exists():
            pass 
        else:
            missing = missing + 1
            print('{}:{}:missing'.format(file, msgid))
    print('Total:{}'.format(len(files)))
    print('Defects:{}'.format(defects))
    print('Missing:{}'.format(missing))
    print('Empty:{}'.format(empty))


def legacy():
    """Gather stats on mhonarc mappings"""
    cutoff = datetime.datetime(2019,1,14)
    for elist in EmailList.objects.filter(private=False, name='ietf'):
        lcount = Legacy.objects.filter(email_list_id=elist.name).count()
        mcount = elist.message_set.filter(date__lte=cutoff).count()
        if lcount < mcount:
            delta = (mcount - lcount) / mcount
        else:
            delta = 0
        if delta > 0.01:
            mark = '**'
        else:
            mark = ''
        print("{:25} {:10} {:10} {:.2f} {:4}".format(elist.name, mcount, lcount, delta, mark))

    
def lookups():
    """Test the message find routines"""
    from mlarchive.archive.view_funcs import find_message_date, find_message_date_reverse, find_message_gbt

    for elist in EmailList.objects.all():
        print("Checking list: {}".format(elist.name))
        sqs = SearchQuerySet().filter(email_list=elist.pk).order_by('date')
        print("-date")
        for m in sqs:
            if find_message_date(sqs,m.object) == -1:
                print("Problem with {}:{}".format(elist.name,m.object.msgid))
        sqs = SearchQuerySet().filter(email_list=elist.pk).order_by('-date')
        print("-date-reverse")
        for m in sqs:
            if find_message_date_reverse(sqs,m.object) == -1:
                print("Problem with {}:{}".format(elist.name,m.object.msgid))
        sqs = SearchQuerySet().filter(email_list=elist.pk).order_by('tdate','date')
        print("-gbt")
        for m in sqs:
            if find_message_gbt(sqs,m.object) == -1:
                print("Problem with {}:{}".format(elist.name,m.object.msgid))

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
                            print("%s: %s" % (pattern.pattern, path))
                        break

def missing_files():
    """Scan messages in date range and report if any are missing the archive file"""
    total = 0
    start = datetime.datetime(2014,0o1,20)
    end = datetime.datetime(2014,0o1,23)
    messages = Message.objects.filter(date__gte=start,date__lte=end)
    for message in messages:
        if not os.path.exists(message.get_file_path()):
            print('missing: %s:%s:%s' % (message.email_list, message.pk, message.date))
            total += 1
    print('%d of %d missing.' % (total, messages.count()))

def missing_from_index(start):
    """Scan messages, starting from updated = start (YYYY-MM-DDTHH:MM:SS),
    and report any that aren't in the search index"""
    start_date = parse(start)
    missing = 0
    messages = Message.objects.filter(updated__gte=start_date)
    for message in messages:
        results = SearchQuerySet().filter(msgid=message.msgid)
        if not results:
            print("Not found: {},{},{},{}".format(
                message.pk,
                message.date,
                message.email_list.name,
                message.msgid))
            missing += 1
    print("Processed: {}".format(messages.count()))
    print("Missing: {}".format(missing))

def mmdfs():
    """Scan all mailbox files and print first lines of MMDF types, looking for
    different styles
    """
    count = 0
    for path in all_mboxs():
        try:
            mb = _classes.get_mb(path)
        except _classes.UnknownFormat:
            pass
        if isinstance(mb,_classes.CustomMMDF):
            with open(path) as f:
                if f.read(10) == '\x01\x01\x01\x01\n\x01\x01\x01\x01\n':
                    print("%s" % path)
                    count += 1
    print("Total: %s" % count)

def message_rfc822():
    """Scan all lists for message/rfc822"""
    for elist in EmailList.objects.all().order_by('name'):
        print("Scanning {}".format(elist.name))

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())
            count = 0
            for part in message.walk():
                if part.get_content_type() == 'message/rfc822':
                    count += 1
                    payload = part.get_payload()
                    if len(payload) != 1 or payload[0].get_content_type() != 'text/plain':
                        print(msg.pk,payload,' '.join([ x.get_content_type() for x in payload]))

            if count > 1:
                print("{}:{}".format(msg.pk,count))

def multipart():
    """Scan all lists, accumulate types which are multipart"""
    types = {}
    for elist in EmailList.objects.all().order_by('name'):
        print("Scanning {}".format(elist.name))

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())
            for part in message.walk():
                if part.is_multipart():
                    types[part.get_content_type()] = types.get(part.get_content_type(),0) + 1

    print(types)


def attachments():
    """Scan all lists, analyze attachments"""
    missing_from_db = 0
    missing_new = {}
    missing_old = {}
    content_dispositions = {}
    total = 0
    lookup_extension('txt/plain')
    mime_types = cache.get('mime_types')
    for elist in EmailList.objects.all().order_by('name'):
        print("Scanning {}".format(elist.name))

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())
            count = 0
            for part in message.walk():
                if is_attachment(part):
                    total = total + 1
                    count = count + 1
                    content_type = part.get_content_type()
                    # content_disposition = part.get_content_disposition()
                    content_disposition = part.get('content-disposition')
                    if content_disposition:
                        content_disposition = content_disposition.split()[0].strip(';')
                    content_dispositions[content_disposition] = content_dispositions.get(content_disposition, 0) + 1
                    if content_type not in mime_types:
                        missing_new[content_type] = missing_new.get(content_type, 0) + 1
                        print("NEW {:10} {}".format(msg.pk, content_type))
                    if content_type not in CONTENT_TYPES:
                        missing_old[content_type] = missing_old.get(content_type, 0) + 1
                        print("OLD {:10} {}".format(msg.pk, content_type))

            if count > msg.attachment_set.count():
                missing_from_db = missing_from_db + (count - msg.attachment_set.count())

    print('Total Attachments: %s' % total)
    print('Missing from DB: %s' % missing_from_db)
    for key, value in list(missing_new.items()):
        print("NEW: %s (%s)" % (key, value))
    for key, value in list(missing_old.items()):
        print("OLD: %s (%s)" % (key, value))
    for key, value in list(content_dispositions.items()):
        print("CONTENT_DISPOSITION: %s (%s)" % (key, value))


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
            print(listname)
        try:
            mb = _classes.get_mb(path)
        except _classes.UnknownFormat:
            print("Unknown format: %s" % path)
            continue

        for i,msg in enumerate(mb):
            total += 1
            recs = msg.get_all('received')
            if not recs:
                norecs += 1
                print("no received header:%s,%s" % (path,i))
                nrmap[path] = nrmap.get(path,0) + 1
                continue
            parts = recs[0].split(';')
            try:
                # take the final bit (almost always 2, but sometimes ";" appears earlier
                date =  _classes.parsedate_to_datetime(parts[-1])
            except IndexError as error:
                print("Failed: %s:%s (%s)" % (path,i,error))
                sys.exit(1)
            if not date:
                print("Total: %s\nnorecs: %s" % (total,norecs))
                print("Failed: %s:%s:%s" % (path,i,recs))
                sys.exit(1)
            elif _classes.is_aware(date):
                aware += 1
    print("Total: %s\nnorecs: %s\naware: %s" % (total,norecs,aware))
    with open('received.log','w') as f:
        for key in nrmap:
            f.write(key + '\n')

def subjects(listname):
    """Return subject line of all messages for listname"""
    for msg in process([listname]):
        print("%s: %s" % (msg.get('date'),msg.get('subject')))

def subject_non_english():
    """Scans for subject lines containing non latin1 characters"""
    count = 0
    for email_list in EmailList.objects.order_by('name'):
        messages = Message.objects.filter(email_list=email_list)
        print("{} ({})".format(email_list.name, messages.count()))
        for msg in messages:
            try:
                subject = msg.subject.encode('latin1')
            except UnicodeEncodeError:
                count += 1
                print("Non latin1 subject {} {} {}".format(msg.pk, msg.msgid,msg.subject))
    print("Total: {}".format(count))

def subject_term_length():
    """Scans for subject terms over Xapian term limit"""
    count = 0
    for email_list in EmailList.objects.order_by('name'):
        messages = Message.objects.filter(email_list=email_list)
        print("{} ({})".format(email_list.name, messages.count()))
        for msg in messages:
            # xapian encodes to utf8
            subject = msg.subject.encode('utf8')
            for word in subject.split():
                if len(word) > MAX_TERM_LENGTH:
                    count += 1
                    print("Term too long {} {}".format(msg.pk, msg.msgid))
    print("Total: {}".format(count))

def same_date():
    """Return messages with the same date of another message in the list"""
    start = datetime.datetime(2016,1,1)
    for elist in EmailList.objects.all().order_by('name'):
        messages = Message.objects.filter(email_list=elist,date__gte=start).order_by('date')
        previous = messages.first()
        for message in messages[1:]:
            if message.date == previous.date:
                print('{}:{}:{}'.format(message.pk,message.date,message.subject))
                print('{}:{}:{}'.format(previous.pk,previous.date,previous.subject))
            previous = message

def run_messagewrapper_process():
    """Call MessageWrapper.process() for each message in the (old) archive, to check
    for errors after changing some underlying code"""
    for msg in all_messages(['ancp']):
        '''follow date() pattern, need to know list, etc, during iteration'''
        pass

def test():
    """Just print count every five seconds to test progress"""
    for n in range(0,10):
        time.sleep(5)
        print(n)

def test_read():
    """Try email.message_from_binary_file on messages"""
    messages = Message.objects.filter(date__year=2019)
    total = messages.count()
    for n, message in enumerate(messages):
        if n % 1000 == 0:
            print('{} of {}'.format(n, total))
        path = message.get_file_path()
        with open(path, 'rb') as fil:
            msg = email.message_from_binary_file(fil)
        if msg.defects:
            print(message.pk, msg.defects)


def non_ascii():
    """Scan all lists looking for non-ascii data in headers to test handling"""
    for elist in EmailList.objects.all().order_by('name'):
    # for elist in EmailList.objects.filter(name='homenet').order_by('name'):
        print("Scanning {}".format(elist.name))

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            message = email.message_from_string(msg.get_body_raw())

            for header in ('from','subject'):
                if not is_ascii(message[header]):
                    print("Message: {},   {}:{}".format(msg.pk,header,message[header]))
                    return


def mime_encoded_word(start):
    """Scan all lists looking for MIME encoded-word (RFC2047) data in headers to test handling"""
    max_bmp = '\U0000ffff'
    total = 0
    for elist in EmailList.objects.all().order_by('name'):
        if start and start > elist.name:
            continue
        print("Scanning {}".format(elist.name))

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            try:
                message = email.message_from_string(msg.get_body_raw())
            except IOError:
                continue

            for header in ('from', 'subject'):
                count = 0
                if message[header] and "=?" in message[header]:
                    total = total + 1
                    parts = email.header.decode_header(message[header])
                    try:
                        unis = [str(string, encoding) for string, encoding in parts if encoding]
                    except (UnicodeDecodeError, LookupError):
                        print("Message: {},   {}:{}  DECODE ERROR".format(msg.pk, header, message[header]))
                        continue
                    
                    # check fo high plane
                    for uni in unis:
                        for point in uni:
                            if point > max_bmp:
                                count = count + 1
                    if count > 0:
                        print("Message: {},   {}:{}  High Plane: {} ".format(msg.pk, header, message[header], 'X' * count))

                    # check if db field empty
                    if getattr(msg, map_header(header)) == '':
                        print("Message: {},   {}:{}  EMPTY".format(msg.pk, header, message[header]))

                    if '=?' in getattr(msg, map_header(header)):
                        print("Message: {},   {}:{}  UNDECODED".format(msg.pk, header, message[header]))
    print("Total: %s" % total)


ecre = re.compile(r'''
  =\?                   # literal =?
  (?P<charset>[^?]*?)   # non-greedy up to the next ? is the charset
  \?                    # literal ?
  (?P<encoding>[qb])    # either a "q" or a "b", case insensitive
  \?                    # literal ?
  (?P<encoded>.*?)      # non-greedy up to the next ?= is the encoded string
  \?=                   # literal ?=
  ''', re.VERBOSE | re.IGNORECASE | re.MULTILINE)


def get_encoded_words():
    """Scan all messages and find those with encoded-words in the headers.  Save list to a file"""
    messages = []
    for elist in EmailList.objects.all().order_by('name'):
        #if start and start > elist.name:
        #    continue
        print("Scanning {}".format(elist.name))

        for msg in Message.objects.filter(email_list=elist).order_by('date'):
            try:
                message = email.message_from_string(msg.get_body_raw())
            except IOError:
                continue

            for header in ('from', 'subject'):
                if message[header] and re.search(ecre, message[header]):
                    messages.append(msg.pk)
                    break
        if messages:
            with open('encoded_messages.txt', 'a') as f:
                data = ','.join([str(n) for n in messages])
                f.write(data + '\n')
            messages = []


def map_header(header):
    if header == 'from':
        return 'frm'
    else:
        return header


def fix_encoded_words(fix=False):
    """Process messages with encoded-words in header"""
    pks = []
    mismatches = []
    with open('encoded_messages.txt') as f:
        line = f.readline()
        while line:
            chop = line[:-1]    # remove newline
            pks.extend(chop.split(','))
            line = f.readline()

    for pk in pks:
        message = Message.objects.get(pk=pk)
        for db_header, header in (('frm', 'from'), ('subject', 'subject')):
            msg = email.message_from_string(message.get_body_raw())
            mw = MessageWrapper(msg, message.email_list.name)
            if msg[header] and '=?' in msg[header]:
                text = mw.normalize(msg[header])
                if text != getattr(message, db_header):
                    mismatches.append(message)
                    if '?="' not in msg[header] and '?=)' not in msg[header] and not has_higher_plane(text):
                        print("PK: %s, %s != %s" % (pk, repr(text), repr(getattr(message, db_header))))
                    if fix:
                        setattr(message, db_header, text)
                        message.save()

    print("Total: %s" % len(pks))
    print("Mismatches: %s" % len(mismatches))


def has_higher_plane(header):
    max_bmp = '\U0000ffff'
    for point in header:
        if point > max_bmp:
            return True
    return False


def month_count():
    """For current lists print total messages per month for last year"""
    now = datetime.datetime.now()
    for elist in EmailList.objects.filter(private=False).order_by('name'):
        end = datetime.datetime(now.year, 1, 1)
        if elist.message_set.filter(date__gte=end):
            for n in range(1, 13):
                start = end - relativedelta(months=1)
                count = elist.message_set.filter(date__gte=start, date__lt=end).count()
                print("{} {}: {}".format(elist.name, start.strftime("%Y %b"), count))
                end = start


def index_test(year_min):
    """Show message breakdown using scheme, lists with < year_min messages / year get
    year page, otherwise monthly"""
    now = datetime.datetime.now()
    active_lists = []
    month100 = 0
    for elist in EmailList.objects.filter(private=False).order_by('name'):
        end = datetime.datetime(now.year, 1, 1)
        start = end - relativedelta(years=1)
        if elist.message_set.filter(date__gte=end).count() > 0:
            active_lists.append(elist)
            year_count = elist.message_set.filter(date__gte=start, date__lt=end).count()
            if year_count < int(year_min):
                # do year page
                print("{} {}: {}".format(elist.name, start.strftime("%Y"), year_count))
            else:
                # otherwise monthly pages
                for n in range(1, 13):
                    start = end - relativedelta(months=1)
                    count = elist.message_set.filter(date__gte=start, date__lt=end).count()
                    print("{} {}: {}".format(elist.name, start.strftime("%Y %b"), count))
                    if count < 100:
                        month100 += 1
                    end = start

    print("Year Minimum: {}".format(year_min))
    print("Total active lists: {}".format(len(active_lists)))
    print("Monthly pages < 100: {}".format(month100))


def year_max():
    """Find email lists with largest message count per year"""
    maximum = 0
    elists = EmailList.objects.annotate(num=Count('message')).order_by('-num')
    for elist in elists[:25]:
        for year in range(2008, 2018):
            count = elist.message_set.filter(date__year=year).count()
            if count > maximum:
                maximum = count
                print("{}:{}:{}".format(elist.name, year, count))


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Run an archive scan.')
    parser.add_argument('-f','--fix',help="perform fix",action='store_true')
    parser.add_argument('function')
    parser.add_argument('extras', nargs=argparse.REMAINDER)
    args = vars(parser.parse_args())
    print(args)
    if args['function'] in globals():
        func = globals()[args['function']]
        kwargs = _get_kwargs(args)
        func(*args['extras'],**kwargs)
    else:
        raise argparse.ArgumentTypeError('no scan function: %s' % args['function'])

def _get_kwargs(args):
    """Get keyword arguments to pass to function"""
    kwargs = args.copy()
    kwargs.pop('function')
    if 'extras' in kwargs:
        kwargs.pop('extras')
    if args['fix'] == False:
        kwargs.pop('fix')
    return kwargs

if __name__ == "__main__":
    main()
