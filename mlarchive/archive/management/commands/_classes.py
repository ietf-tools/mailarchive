import base64
import datetime
import email
import glob
import hashlib
import mailbox
import os
import pytz
import re
import shutil
import string
import subprocess
import tempfile
import uuid
from collections import deque
from email.utils import parsedate_tz, getaddresses, make_msgid

from django.conf import settings
from django.core.management.base import CommandError
from dateutil.tz import tzoffset

from mlarchive.archive.models import Attachment, EmailList, Legacy, Message, Thread
from mlarchive.archive.management.commands._mimetypes import CONTENT_TYPES, UNKNOWN_CONTENT_TYPE
from mlarchive.archive.inspectors import *
from mlarchive.utils.decorators import check_datetime
from mlarchive.utils.encoding import decode_safely, decode_rfc2047_header

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

'''
Notes on character encoding.

In general we want work with unicode strings.  To do this it's important to do encoding
and decoding of Unicode at the furthest boundary of the interface.

Standards do not allow for non-ascii data in email headers 2822 (822).  RFC2047 defines
extensions to allow non-ascii text data in headers through the use of encoded-words.
Nevertheless, we find non-ascii data in email headers and need to handle this
consistently.  See scan ##

When parsing an email message Python2 email module returns a byte-string for header
values

In [23]: x.get('subject')
Out[23]: 'Voc\xea recebeu um Vivo Torpedo SMS'

'''


# --------------------------------------------------
# Globals
# --------------------------------------------------
date_formats = ["%a %b %d %H:%M:%S %Y",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%a %b %d %H:%M:%S %Y %Z"]

MBOX_SEPARATOR_PATTERN = re.compile(r'^From .* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
SEPARATOR_PATTERNS = [ re.compile(r'^Return-[Pp]ath:'),
                       re.compile(r'^Envelope-to:'),
                       re.compile(r'^Received:'),
                       re.compile(r'^X-Envelope-From:'),
                       re.compile(r'^From:'),
                       re.compile(r'^Date:'),
                       re.compile(r'^To:'),
                       re.compile(r'^Path:'),
                       re.compile(r'^20[0-1][0-9]$') ]      # odd one, see forces

HEADER_PATTERN = re.compile(r'^[\041-\071\073-\176]{1,}:')
SENT_PATTERN = re.compile(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+(\d{1,2})/(\d{1,2})/(\d{4,4})\s+(\d{1,2}):(\d{2,2})\s+(AM|PM)')
MSGID_PATTERN = re.compile(r'<([^>]+)>')                    # [^>] means any character except ">"
ENVELOPE_DATE_PATTERN = re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
ENVELOPE_DUPETZ_PATTERN = re.compile(r'[\-\+]\d{4} \([A-Z]+\)$')

subj_blob_pattern = r'(\[[\040-\132\134\136-\176]{1,}\]\s*)'
subj_refwd_pattern = r'([Rr][eE]|F[Ww][d]?)\s*' + subj_blob_pattern + r'?:\s'
subj_leader_pattern = subj_blob_pattern + r'*' + subj_refwd_pattern
subj_blob_regex = re.compile(r'^' + subj_blob_pattern)
subj_leader_regex = re.compile(r'^' + subj_leader_pattern)

# --------------------------------------------------
# Custom Exceptions
# --------------------------------------------------
class DateError(Exception):
    # failed to parse the message date
    pass

class DuplicateMessage(Exception):
    # Duplicate Message-id
    pass

class GenericWarning(Exception):
    pass

class NoHeaders(Exception):
    # the message contains no header fields, usually indicates problem with parsing
    pass

class UnknownFormat(Exception):
    # the mail file format is unrecognized
    pass

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def archive_message(data,listname,private=False,save_failed=True):
    """This function is the internals of the interface to Mailman.  It is called by the
    standalone script archive-mail.py.  Inputs are:
    data: the message as a string (comes from sys.stdin.read())
    listname: a string, provided as command line argument to archive-mail
    private: boolean, True if the list is private.  Only used if this is a new list
    save_failed: default is True, set to false when calling from compare utility script
    """
    try:
        msg = email.message_from_string(data)
        mw = MessageWrapper(msg,listname,private=private)
        mw.save()
    except DuplicateMessage as error:
        # if DuplicateMessage it's already been saved to _dupes
        logger.error('Archive message failed [{0}]'.format(error.args))
        return 0
    except SpamMessage as error:
        # if SpamMessage it's already been saved to _spam
        logger.error('Archive message failed [{0}]'.format(error.args))
        return 0
    except Exception as error:
        logger.error('Archive message failed [{0}]'.format(error.args))
        if not save_failed:
            return 1
        if msg:
            save_failed_msg(msg,listname,error)
        else:
            save_failed_msg(data,listname,error)
        return 1    # TODO: other error?
    return 0

def clean_spaces(s):
    """Reduce all whitespaces to one space"""
    s = re.sub(r'\s+',' ',s)
    return s

def flatten_message(msg):
    """Returns the message flattened to a string, for use in writing to a file.  NOTE:
    use this instead of message.as_string() to avoid mangling message.
    """
    from cStringIO import StringIO
    from email.generator import Generator
    fp = StringIO()
    g = Generator(fp, mangle_from_=False)
    g.flatten(msg)
    return fp.getvalue()

def get_base_subject(text):
    """Returns 'base subject' of a message.  This is the subject which has specific
    subject artifacts removed.  This function implements the algorithm defined in
    section 2.1 of RFC5256
    """
    # step 1 - now all handled by normalize
    # uni = decode_rfc2047_header(text)
    # utf8 = uni.encode('utf8')
    # text = clean_spaces(utf8)
    # text = text.rstrip()

    while True:
        # step 2
        while text.endswith('(fwd)'):
            text = text[:-5].rstrip()

        while True:
            # step 3
            textin = text
            text = subj_leader_regex.sub('',text)

            # step 4
            m = subj_blob_regex.match(text)
            if m:
                temp = subj_blob_regex.sub('',text)
                if temp:
                    text = temp
            if text == textin:    # step 5 (else repeat 3 & 4)
                break

        # step 6
        if text.startswith('[Fwd:') and text.endswith(']'):
            text = text[5:-1]
            text = text.strip()
        else:
            break

    return text

def get_envelope_date(msg):
    """Returns the date, a naive or aware datetime object, from the message
    envelope line.  msg is a email.message.Message object

    NOTE: Some files have mangled email addresses in "From" line:
    iesg/2008-01.mail: From dromasca at avaya.com  Tue Jan  1 04:49:41 2008
    """
    line = get_from(msg)
    if not line:
        return None

    match = ENVELOPE_DATE_PATTERN.search(line)
    if match:
        date = match.group()
    else:
        return None

    return parsedate_to_datetime(date)

def get_from(msg):
    """Returns the 'from' line of message.  This function is required because of the
    disparity between different message objects.  email.message.Message has a
    get_unixfrom() method while mailbox.mboxMessage has both get_unixfrom() and
    a get_from() method, but the get_unixfrom() returns None
    """
    if hasattr(msg, 'get_from'):
        frm = msg.get_from()
        if frm:
            return frm
    if hasattr(msg, 'get_unixfrom'):
        frm = msg.get_unixfrom()
        if frm:
            return frm

def get_header_date(msg):
    """Returns the date, a naive or aware datetime object, from the message header.
    First checks the 'Date:' field, then 'Sent:'.  Returns None if it can't locate
    and interpret either of these.
    """
    date = msg.get('date')
    if not date:
        date = msg.get('sent')
    if not date:
        return None
    return parsedate_to_datetime(date)

def get_incr_path(path):
    """Return path with unused incremental suffix"""
    files = glob.glob(path + '.*')
    if files:
        files.sort()
        sequence = str(int(files[-1][-4:]) + 1)
    else:
        sequence = '0'
    return path + '.' + sequence.zfill(4)

def get_mb(path):
    """Returns a mailbox object based on the first line of the file.
    "From " -> Custom Type
    "^A^A^A^A" -> MMDF
    [another header line] -> Custom Type
    """
    with open(path) as f:
        line = f.readline()
        while not line or line == '\n':
            line = f.readline()
        if line.startswith('From '):                # most common mailbox type, MBOX
            return CustomMbox(path,separator=MBOX_SEPARATOR_PATTERN)
        elif line == '\x01\x01\x01\x01\n':          # next most common type, MMDF
            return CustomMMDF(path)
        for pattern in SEPARATOR_PATTERNS:          # less common types
            if pattern.match(line):
                return CustomMbox(path,separator=pattern)

    # if we get here the file isn't recognized.  Raise an error
    raise UnknownFormat('%s, %s' % (path,line))

def get_mime_extension(type):
    """Returns the proper file extension for the given mime content type (string),
    returns a tuple of extension, description
    """
    if type in CONTENT_TYPES:
        ext,desc = CONTENT_TYPES[type]
        # return only the first of multiple extensions
        return (ext.split(',')[0], desc)
    # TODO: type without x
    elif type.startswith('text/'):
        return ('txt','Text Data')
    else:
        return (UNKNOWN_CONTENT_TYPE,type)

def get_received_date(msg):
    """Returns the date from the received header field.  Date field is last field
    using semicolon as separator, per RFC 2821 Section 4.4.  parsedate_to_datetime
    returns a timezone aware date if date includes timezone info, otherwise a
    naive date.  Use the most recent Received field, first in list returned by get_all()
    """
    recs = msg.get_all('received')
    if not recs:
        return None
    else:
        return parsedate_to_datetime(recs[0].split(';')[-1])

def is_aware(date):
    """Returns True if the date object passed in timezone aware, False if naive.
    See http://docs.python.org/2/library/datetime.html section 8.1.1
    """
    if not isinstance(date,datetime.datetime):
        return False
    if date.tzinfo and date.tzinfo.utcoffset(date) is not None:
        return True
    return False

def parsedate_to_datetime(date):
    """Returns a datetime object from string.  May return naive or aware datetime.

    This function is from email standard library v3.3, converted to 2.x
    http://python.readthedocs.org/en/latest/library/email.util.html
    """
    try:
        tuple = parsedate_tz(date)
        if not tuple:
            return None
        tz = tuple[-1]
        if tz is None:
            return datetime.datetime(*tuple[:6])
        return datetime.datetime(*tuple[:6],tzinfo=tzoffset(None,tz))
    except ValueError:
        return None

def save_failed_msg(data,listname,error):
    """Called when an attempt to import a message fails.  "data" will typically be an
    instance of email.message.Message.  In some odd case where message parsing fails
    "data" will be a string (this should never happen because the email.parser excepts
    even empty strings).  Log error entry should contain useful information about the
    error, the message identity and the filename it is being saved under
    """
    # get filename
    path = EmailList.get_failed_dir(listname)
    basename = datetime.datetime.today().strftime('%Y-%m-%d')
    files = glob.glob(os.path.join(path,basename + '.*'))
    if files:
        files.sort()
        sequence = str(int(files[-1][-4:]) + 1)
    else:
        sequence = '0'
    filename = basename + '.' + sequence.zfill(4)

    # log entry
    if isinstance(data,email.message.Message):
        output = flatten_message(data)
        identifier = data.get('Message-ID','')
        if not identifier:
            identifier = get_from(data)
    else:
        output = data
        identifier = ''
    log_msg = "Import Error [{0}, {1}, {2}]".format(os.path.join(path,filename),(error.__class__,error.args),identifier)
    logger.error(log_msg)

    write_file(os.path.join(path,filename),output)

def call_remote_backup(path):
    """If REMOTE_BACKUP_DIR is defined copies the message specified in path to the
    local backup archive directory, creating subdirectories as needed.  Else checks for
    REMOTE_BACKUP_COMMAND, and calls this command with path as the first argument"""
    if hasattr(settings,'REMOTE_BACKUP_DIR'):
        # strip relative path
        parts = path.split('/')
        if parts[-2].startswith('_'):
            relative_path = os.path.join(*parts[-3:])
        else:
            relative_path = os.path.join(*parts[-2:])
        target_path = os.path.join(settings.REMOTE_BACKUP_DIR,relative_path)
        directory = os.path.dirname(target_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
            os.chmod(directory,02777)
        shutil.copy2(path,target_path)

    elif hasattr(settings,'REMOTE_BACKUP_COMMAND'):
        backup_command = settings.REMOTE_BACKUP_COMMAND
        try:
            subprocess.check_call([backup_command,path])
        except (OSError,subprocess.CalledProcessError) as error:
            logger.error('Error calling remote backup command ({})'.format(error))

def write_file(path,data):
    """Function to write file to disk.
    - creates directory if it doesn't exist
    - saves file
    - sets mode of file
    - calls external backup script if defined
    """
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        os.makedirs(directory)
        os.chmod(directory,02777)
    with open(path,'w') as f:
        f.write(data)
        f.flush()
    os.chmod(path,0666)
    #call_remote_backup(path)

# --------------------------------------------------
# Classes
# --------------------------------------------------
class CustomMMDF(mailbox.MMDF):
    """Custom implementation of mailbox.MMDF.  The original class from the standard
    library is flawed in that it uses the same get_message() function as mailbox.mbox,
    which consumes the first line of the message as the "From " line envelope header.
    The MMDF format has "^A^A^A^A" postmark that separates messages, but these are
    already excluded in the _toc.
    """
    def get_message(self, key):
        """Return a Message representation or raise a KeyError."""
        start, stop = self._lookup(key)
        self._file.seek(start)
        #from_line = self._file.readline().replace(os.linesep, '')
        string = self._file.read(stop - self._file.tell())
        msg = self._message_factory(string.replace(os.linesep, '\n'))
        #msg.set_from(from_line[5:])
        return msg

class CustomMbox(mailbox.mbox):
    """Custom mbox class that improves message parsing.  Expects the separator keyword
    argument which is a compiled regex object representing the new message indicator.

    A standard mbox will match this expression
    '^From .* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+'

    NOTE: we exclude false matches to lines like:
    From your message Mon, 9 Nov 1998 06:09:48 -0000:

    There are numerous mailbox files where messages simply lead with the same header
    field.  For example:
    '^Return-[Pp]ath:'
    '^Envelope-to:'

    NOTE: in all cases the matched line must be preceeded by a blank line
    """
    def __init__(self, *args, **kwargs):
        self._separator = kwargs.pop('separator')
        self._false_separator = re.compile(r'^From .* message (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
        # can't use super because mbox is old style class
        mailbox.mbox.__init__(self, *args, **kwargs)

    def _generate_toc(self):
        """Generate key-to-(start, stop) table of contents."""
        starts, stops = [], []
        lines = deque(' ',maxlen=2)
        self._file.seek(0)
        while True:
            line_pos = self._file.tell()
            lines.append(self._file.readline())
            if self._separator.match(lines[1]) and not lines[0].strip() and not self._false_separator.match(lines[1]):
                if len(stops) < len(starts):
                    stops.append(line_pos - len(os.linesep))
                starts.append(line_pos)
            elif lines[1] == '':
                stops.append(line_pos)
                break
        self._toc = dict(enumerate(zip(starts, stops)))
        self._next_key = len(self._toc)
        self._file_length = self._file.tell()

    def get_message(self, key):
        """Return a Message representation or raise a KeyError."""
        has_from = True
        start, stop = self._lookup(key)
        self._file.seek(start)
        from_line = self._file.readline().replace(os.linesep, '')
        if HEADER_PATTERN.match(from_line):
            self._file.seek(start)              # reset pointer to keep first header line
            has_from = False
        string = self._file.read(stop - self._file.tell())
        msg = self._message_factory(string.replace(os.linesep, '\n'))
        if has_from:
            msg.set_from(from_line)
        return msg

class Loader(object):
    """Object which handles loading messages from a mailbox file.  filename is the name
    of the file to load.  Accepts the following keyword options:

    dryrun: if True just perform parsing, no saves
    firstrun: True if this is the initial load, skips messages not in "legacy" table
    listname: the name of the email list we are loading messages for
    private: True is this is a private list
    test: if True don't save the message to disk archive (only to database)

    NOTE: if the message is from the last 30 days we skip firstrun step, because there
    will be some lag between when the legacy archive index was created and the
    firstrun import completes.  The check will also be skipped if msgid was not
    found in the original message and we had to create one, becasue it obviously
    won't exist in the web archive.
    """
    def __init__(self, filename, **options):
        self.filename = filename
        self.options = options
        self.stats = {'count': 0, 'errors': 0, 'spam': 0, 'bytes_loaded': 0}
        self.private = options.get('private')
        self.listname = options.get('listname')
        self.mb = get_mb(filename)
        self.klass = self.mb.__class__.__name__
        self.stats[self.klass] = self.stats.get(self.klass, 0) + 1

        logger.info('loader called with: %s' % self.filename)

    def _cleanup(self):
        """Call this function when you are done with the loader object
        """
        #logger.info('size: %s, loaded: %s' % (self.mb._file_length,self.stats['bytes_loaded']))
        self.mb.close()

    def _load_message(self,msg):
        """Use MessageWrapper to save a Message to the archive.
        """
        self.stats['count'] += 1
        try:
            mw = MessageWrapper(msg, self.listname, private=self.private)
        except Exception as e:
            import sys
            raise type(e), type(e)(e.message + ' happens at {} with text: {}'.format(self.filename,msg.as_string()[:120])), sys.exc_info()[2]

        # filter using Legacy archive
        if self.options.get('firstrun') and mw.date < (datetime.datetime.now() - datetime.timedelta(days=30)) and mw.created_id == False:
            legacy = Legacy.objects.filter(msgid=mw.msgid,email_list_id=self.listname)
            if not legacy:
                self.stats['spam'] += 1
                if not (self.options.get('dryrun') or self.options.get('test')):
                    mw.write_msg(subdir='_filtered')
                return

        # process message
        mw.archive_message
        self.stats['bytes_loaded'] += mw.bytes

        if not self.options.get('dryrun'):
            mw.save(test=self.options.get('test'))

    def process(self):
        """If the "break" option is set propogate the exception
        """
        for m in self.mb:
            try:
                self._load_message(m)
            except DuplicateMessage as error:
                logger.warning("Import Warn [{0}, {1}, {2}]".format(self.filename,error.args,get_from(m)))
            except Exception as error:
                save_failed_msg(m,self.listname,error)
                self.stats['errors'] += 1
                if self.options.get('break'):
                    raise

        self._cleanup()

class MessageWrapper(object):
    """This class takes a email.message.Message object (email_message) and listname as
    a string and constructs the mlarchive.archive.models.Message (archive_message) object.
    Use the save() method to save the message in the archive.

    Use lazy initialization.  On init only get message-id.  If this message is being
    filtered by message id, no use performing rest of message parsing.  This means you
    must explicitly call process() or access the archive_message object for the object
    to contain valid data.
    """
    def __init__(self, email_message, listname, private=False, backup=True):
        self._archive_message = None
        self._date = None
        self.created_id = False
        self.email_message = email_message
        self.hashcode = None
        self.listname = listname
        self.private = private
        self.spam_score = 0
        self.bytes = len(flatten_message(email_message))

        # fail right away if no headers
        if not self.email_message.items():         # no headers, something is wrong
            raise NoHeaders

        self.msgid = self.get_msgid()

    def _get_archive_message(self):
        """Returns the archive.models.Message instance"""
        if self._archive_message is None:
            self.process()
        return self._archive_message
    archive_message = property(_get_archive_message)

    def _get_date(self):
        if not self._date:
            self._date = self.get_date()
        return self._date
    date = property(_get_date)

    @staticmethod
    def get_addresses(text):
        """Returns a string of realname and email address RFC2822 addresses from a
        string suitable for a To or CC header
        """
        result = []
        tuples = getaddresses([decode_rfc2047_header(text)]) # getaddresses takes a sequence
        for name,address in tuples:                          # flatten list of tuples
            if name:
                result.append(name)
            if address:
                result.append(address)
        return ' '.join(result)

    def get_cc(self):
        """Returns the CC field realname and email addresses"""
        cc = self.email_message.get('cc')
        if not cc:
            return ''
        return self.get_addresses(cc)

    @check_datetime
    def get_date(self):
        """Returns the message date.  It takes an email.Message object and returns a naive
        Datetime object in UTC time.

        First we inspect the first Received header field since the format is consistent
        and the time is actually more reliable then the time on the message.
        Next check the Date: header field, Unfortunately the Date header
        can vary dramatically in format or even be missing.  Finally check the envelope
        date.

        NOTE: in a test run we can find the date in the Received header in
        2366079 of 2426328 records, 97.5% of the time (all but 2 were timezone aware)
        """
        for func in (get_received_date,get_header_date,get_envelope_date):
            date = func(self.email_message)
            if date:
                if is_aware(date):
                    #try:
                    return date.astimezone(pytz.utc).replace(tzinfo=None)   # return as naive UTC
                    #except ValueError:
                    #    pass
                else:
                    return date
        else:
            # can't really proceed without a date, likely indicates bigger parsing error
            raise DateError("%s, %s" % (self.msgid,self.email_message.get_unixfrom()))

    def get_hash(self):
        """Returns the message hashcode, a SHA-1 digest of the Message-ID and listname.
        Similar to the popular Web Email Archive, mail-archive.com
        see: https://www.mail-archive.com/faq.html#msgid
        """
        sha = hashlib.sha1(self.msgid)
        sha.update(self.listname)
        return base64.urlsafe_b64encode(sha.digest())

    def get_msgid(self):
        msgid = self.normalize(self.email_message.get('Message-ID',''))
        if msgid:
            msgid = msgid.strip('<>')
        else:
            # see if this is a resent Message, which sometimes have missing Message-ID field
            resent_msgid = self.email_message.get('Resent-Message-ID')
            if resent_msgid:
                msgid = resent_msgid.strip('<>')
        if not msgid:
            msgid = make_msgid('ARCHIVE')
            self.created_id = True
            self.spam_score = self.spam_score | settings.MARK_BITS['NO_MSGID']
            # add message-id to email_message headers so it gets to disk file
            if 'message-id' in self.email_message:
                self.email_message.replace_header('Message-ID',msgid)
            else:
                self.email_message.add_header('Message-ID',msgid)
            #raise GenericWarning('No MessageID (%s)' % self.email_message.get_from())
        return msgid

    def get_subject(self):
        """Gets the message subject.  If the subject looks like spam, long line with
        no spaces, truncate it so as not to cause index errors
        """
        subject = self.normalize(self.email_message.get('Subject',''))
        # TODO: spam?
        #if len(subject) > 120 and len(subject.split()) == 1:
        #    subject = subject[:120]
        return subject

    def get_to(self):
        """Returns the To field realname and email addresses"""
        to = self.email_message.get('to')
        if not to:
            return ''
        return self.get_addresses(to)

    def get_thread(self):
        """This is a simplified version of the Zawinski threading algorithm.
        The process is:
        1) If there are References, lookup the first message-id in the list and return
           it's thread.  If the message isn't found try the next message-id, repeat.
           According to RFC1036 the references list is ordered oldest first.  To start
           searching from the nearest thread sibling reverse the list.
        2) If 'In-Reply-To-' is set, look up that message and return it's thread id.
        3) If the subject line has a "Re:" prefix look for the message matching
           base-subject and return it's thread
        4) If none of the above, return a new thread id

        Messages must be loaded in chronological order for this to work properly.

        Referecnces:
        - http://www.jwz.org/doc/threading.html
        - http://tools.ietf.org/html/rfc5256
        """

        # try References
        if self.references:
            msgids = re.findall(MSGID_PATTERN,self.references)
            for msgid in msgids:
                try:
                    message = Message.objects.get(msgid=msgid)
                    return message.thread
                except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                    pass

        # try In-Reply-to.  Use first msgid found, typically only one
        if self.in_reply_to:
            msgids = re.findall(MSGID_PATTERN,self.in_reply_to)
            if msgids:
                try:
                    message = Message.objects.get(msgid=msgids[0])
                    return message.thread
                except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                    pass

        # check subject
        if self.subject != self.base_subject:
            messages = Message.objects.filter(email_list=self.email_list,
                                              date__lt=self.date,
                                              subject=self.base_subject).order_by('-date')
            if messages:
                return messages[0].thread

        # return a new thread
        return Thread.objects.create(date=self.date)

    def normalize(self, header_text):
        """This function takes some header_text as a string.
        It returns the string decoded and normalized.
        Checks if the header needs decoding:
        - if text contains encoded_words, "=?", use decode_rfc2047_header()
        - or call decode_safely
        - finally, compress whitespace characters to one space
        """
        if not header_text:                  # just return if we are passed an empty string
            return header_text

        # TODO: need this?
        #if type(header_text) is unicode:    # return if already unicode
        #    return header_text              # ie. get_filename() for example sometimes returns unicode

        if '=?' in header_text:              # handle RFC2047 encoded-words
            normal = decode_rfc2047_header(header_text)
        else:
            normal = decode_safely(header_text)

        # encode as UTF8 and compress whitespace
        # normal = normal.encode('utf8')        # this is unnecessary
        normal = clean_spaces(normal)
        return normal.rstrip()

    def process(self):
        """Perform the rest of the parsing and construct the Message object.  Note,
        we are not saving the object to the database.  This happens in the save() function.
        """
        self.email_list,created = EmailList.objects.get_or_create(
            name=self.listname,defaults={'description':self.listname,'private':self.private})
        self.hashcode = self.get_hash()
        self.in_reply_to = self.email_message.get('In-Reply-To','')
        self.references = self.email_message.get('References','')
        self.subject = self.get_subject()
        self.base_subject = get_base_subject(self.subject)
        self.thread = self.get_thread()
        self.from_line = self.normalize(get_from(self.email_message)) or ''
        if self.from_line:
            self.from_line = self.from_line[5:].lstrip()    # we only need the unique part
        self.frm = self.normalize(self.email_message.get('From',''))
        if len(self.frm) > 125:
            # TODO
            # makrkbits
            pass
        self._archive_message = Message(base_subject=self.base_subject,
                             cc=self.get_cc(),
                             date=self.date,
                             email_list=self.email_list,
                             frm = self.frm,
                             from_line = self.from_line,
                             hashcode=self.hashcode,
                             in_reply_to=self.in_reply_to,
                             msgid=self.msgid,
                             references=self.references,
                             spam_score=self.spam_score,
                             subject=self.subject,
                             thread=self.thread,
                             to=self.get_to())
        # not saving here.

    def process_attachments(self, test=False):
        """Walks the message parts and saves any attachments
        """
        for part in self.email_message.walk():
            # TODO can we have an attachment without a filename (content disposition) ??
            name = part.get_filename()
            type = part.get_content_type()
            if name and type in CONTENT_TYPES:     # indicates an attachment
                extension,description = get_mime_extension(type)

                # create record
                attach = Attachment.objects.create(message=self.archive_message,
                                                   description=description,
                                                   name=name)

                # handle unrecognized
                payload = part.get_payload(decode=True)
                if not payload:
                    attach.error = '<<< %s; name=%s: Unrecognized >>>' % (type,name)
                    attach.save()
                    continue

                # write to disk
                if not test:
                    fp = tempfile.NamedTemporaryFile(dir=self.archive_message.get_attachment_path(),
                                                     prefix=extension,
                                                     suffix='.' + extension,
                                                     delete=False)
                    with fp as f:
                        f.write(payload)
                    attach.filename = os.path.basename(fp.name)
                    attach.save()
                    os.chmod(fp.name,0666)
                    call_remote_backup(fp.name)

    def save(self, test=False):
        """Ensure message is not duplicate message-id or hash.  Save message to database.
        Save to disk (if not test mode) and process attachments.
        """
        # check for spam
        if hasattr(settings, 'INSPECTORS'):
            for inspector_name in settings.INSPECTORS:
                inspector_class = eval(inspector_name)
                inspector = inspector_class(self)
                inspector.inspect()

        # check for duplicate message id, and skip
        if Message.objects.filter(msgid=self.msgid,email_list__name=self.listname):
            self.write_msg(subdir='_dupes')
            raise DuplicateMessage('Duplicate msgid: %s' % self.msgid)

        # check for duplicate hash
        if Message.objects.filter(hashcode=self.hashcode):
            self.write_msg(subdir='_dupes')
            raise CommandError('Duplicate hash, msgid: %s' % self.msgid)

        # ensure message has been processed
        _ = self.archive_message

        # write message to disk and then save, post_save signal calls indexer
        # which requires file to be present
        if not test:
            self.write_msg()
        self.archive_message.save()

        # now that the archive.Message object is created we can process any attachments
        self.process_attachments(test=test)

    def write_msg(self,subdir=None):
        """Write a copy of the original email message to the disk archive.
        Use optional argument subdir to specify a subdirectory within the list directory
        ie. "_filtered" or "_failure"
        """
        # set filename
        filename = self.hashcode
        if not filename:
            filename = str(uuid.uuid4())

        # build path
        if subdir:
            path = os.path.join(settings.ARCHIVE_DIR,self.listname,subdir,filename)
        else:
            path = os.path.join(settings.ARCHIVE_DIR,self.listname,filename)

        # if the file already exists, append a suffix
        if os.path.exists(path):
            log_msg = "Message file already exists [{0}]".format(path)
            logger.warning(log_msg)
            path = get_incr_path(path)

        # convert line endings to crlf
        output = re.sub("\r(?!\n)|(?<!\r)\n", "\r\n", flatten_message(self.email_message))

        # write file
        write_file(path,output)
