from django.conf import settings
from django.core.management.base import CommandError
from dateutil.tz import tzoffset
from email.header import decode_header
from email.utils import parsedate, parsedate_tz, mktime_tz, getaddresses, make_msgid
from mlarchive.archive.models import *
from mlarchive.archive.management.commands._mimetypes import *
from mlarchive.utils.decorators import check_datetime
from tzparse import tzparse

from collections import deque

import base64
import datetime
import hashlib
import mailbox
import os
import pytz
import random
import re
import string
import time
import uuid

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# Suppress database warnings
#from warnings import filterwarnings
#filterwarnings('ignore', category = MySQLdb.Warning)

# --------------------------------------------------
# Globals
# --------------------------------------------------

# spam_score bits
MARK_BITS = { NON_ASCII_HEADER:0b0001,
              NO_RECVD_DATE:0b0010,
              NO_MSGID:0b0100,
              HAS_HTML_PART:0b1000 }

SEPARATOR_PATTERNS = [ re.compile(r'^Return-[Pp]ath:'),
                       re.compile(r'^Envelope-to:'),
                       re.compile(r'^Received:'),
                       re.compile(r'^X-Envelope-From:'),
                       re.compile(r'^From:'),
                       re.compile(r'^Date:'),
                       re.compile(r'^To:'),
                       re.compile(r'^20[0-1][0-9]$') ]      # odd one, see forces

HEADER_PATTERN = re.compile(r'^[\041-\071\073-\176]{1,}:')
SENT_PATTERN = re.compile(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+(\d{1,2})/(\d{1,2})/(\d{4,4})\s+(\d{1,2}):(\d{2,2})\s+(AM|PM)')
MSGID_PATTERN = re.compile(r'<([^>]+)>')                    # [^>] means any character except ">"

subj_blob_pattern = r'(\[[\040-\132\134\136-\176]{1,}\]\s*)'
subj_refwd_pattern = r'([Rr][eE]|F[Ww][d]?)\s*' + subj_blob_pattern + r'?:\s'
subj_leader_pattern = subj_blob_pattern + r'*' + subj_refwd_pattern
subj_blob_regex = re.compile(r'^' + subj_blob_pattern)
subj_leader_regex = re.compile(r'^' + subj_leader_pattern)

#subj_leader = r'^(\[[\040-\132\134\136-\176]{1,}\]\s*)*([Rr][eE]|F[Ww][d]?)\s*(\[[\040-\132\134\136-\176]{1,}\]\s*)?:\s'

# --------------------------------------------------
# Custom Exceptions
# --------------------------------------------------
class DateError(Exception):
    # failed to parse the message date
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
def archive_message(msg,listname,private=False):
    mw = MessageWrapper(msg,listname,private=private)
    mw.save()

def clean_spaces(s):
    "Reduce all whitespaces to one space"
    s = re.sub(r'\s+',' ',s)
    return s

def decode_rfc2047_header(h):
    return ' '.join(decode_safely(s, charset) for s, charset in decode_header(h))

def decode_safely(s, charset='latin-1'):
    "Return s decoded according to charset, but do so safely."
    try:
        # return s.decode(charset or 'ascii', 'ignore')
        return unicode(s,charset or 'latin-1')
    except LookupError: # bogus charset
        # return s.decode('ascii','ignore')
        return unicode(s,'latin-1','replace')

def get_base_subject(str):
    '''
    Get the "base subject" of a message.  This is the subject which has specific subject artifacts
    removed.  This function implements the algorithm defined in section 2.1 of RFC5256
    '''
    # step 1 - now all handled by normalize
    # uni = decode_rfc2047_header(str)
    # utf8 = uni.encode('utf8')
    # str = clean_spaces(utf8)
    # str = str.rstrip()

    while True:
        # step 2
        while str.endswith('(fwd)'):
            str = str[:-5].rstrip()

        while True:
            # step 3
            strin = str
            str = subj_leader_regex.sub('',str)

            # step 4
            m = subj_blob_regex.match(str)
            if m:
                temp = subj_blob_regex.sub('',str)
                if temp:
                    str = temp
            if str == strin:    # step 5 (else repeat 3 & 4)
                break

        # step 6
        if str.startswith('[Fwd:') and str.endswith(']'):
            str = str[5:-1]
            str = str.strip()
        else:
            break

    return str

def get_envelope_date(msg):
    '''
    This function takes a email.message.Message object and returns a datetime object
    derived from the envelope header
    '''
    line = msg.get_from()
    if not line:
        return None

    if '@' in line:
        return parsedate_to_datetime(' '.join(line.split()[1:]))
    elif parsedate_to_datetime(line):    # sometimes Date: is first line of MMDF message
        return parsedate_to_datetime(line)

def get_header_date(msg):
    '''
    This function takes a email.message.Message object and tries to parse the date from the
    Date: header field.  It returns a Datetime object, either naive or aware, if it can,
    otherwise None.
    '''
    date = msg.get('date')
    if not date:
        date = msg.get('sent')

    if not date:
        return None

    result = parsedate_to_datetime(date)
    if result:
        return result

    # try tzparse for some odd formations
    date_formats = ["%a %d %b %y %H:%M:%S-%Z",
                    "%d %b %Y %H:%M-%Z",
                    "%Y-%m-%d %H:%M:%S",
                    #"%a %b %d %H:%M:%S %Y",
                    #"%a %b %d %H:%M:%S %Y %Z",
                    #"%a, %d %b %Y %H:%M:%S %Z"
                    ]
    for format in date_formats:
        try:
            result = tzparse(date,format)
            if result:
                return result
        except ValueError:
            pass

    # try some known patterns that require transformation
    try:
        return datetime.datetime.strptime(date,'%A, %B %d, %Y %I:%M %p')
    except ValueError:
        pass

    match = SENT_PATTERN.match(date)
    if match:
        date_string = '{0} {1}/{2}/{3} {4}:{5} {6}'.format(match.group(1),
                                                           match.group(2).zfill(2),
                                                           match.group(3).zfill(2),
                                                           match.group(4),
                                                           match.group(5),
                                                           match.group(6),
                                                           match.group(7))

        return datetime.datetime.strptime(date_string,'%a %m/%d/%Y %I:%M %p')

def get_mb(path):
    '''
    This function takes the path to a file and returns a mailbox object
    and format.  Currently supported types are:
    - mailbox.mmdf
    - BetterMbox (derived from mailbox.mbox)
    - CustomMbox (like mbox but no from line)
    '''
    with open(path) as f:
        line = f.readline()
        while not line or line == '\n':
            line = f.readline()
        if line.startswith('From '):
            return BetterMbox(path)
        elif line == '\x01\x01\x01\x01\n':
            return mailbox.MMDF(path)
        for pattern in SEPARATOR_PATTERNS:
            if pattern.match(line):
                return CustomMbox(path,separator=pattern)

    # if we get here the file isn't recognized.  Raise an error
    raise UnknownFormat('%s, %s' % (path,line))

def get_mime_extension(type):
    '''
    Looks up the proper file extension for the given mime content type (string),
    returns a tuple of extension, description
    '''
    if type in CONTENT_TYPES:
        return CONTENT_TYPES[type]
    # TODO: type without x
    elif type.startswith('text/'):
        return ('txt','Text Data')
    else:
        return (UNKNOWN_CONTENT_TYPE,type)

def get_received_date(msg):
    '''
    This function takes a email.message.Message object and returns a datetime object
    derived from the Received header or else None
    '''
    rec = msg.get('received')
    if not rec:
        return None

    parts = rec.split(';')
    try:
        return parsedate_to_datetime(parts[1])
    except IndexError:
        return None

def is_aware(dt):
    '''
    This function takes a datetime object and returns True if the object is aware, False if
    it is naive
    '''
    if not isinstance(dt,datetime.datetime):
        return False
    if dt.tzinfo and dt.tzinfo.utcoffset(dt) is not None:
        return True
    return False

def parsedate_to_datetime(data):
    '''
    This function is from email standard library v3.3, converted to 2.x
    '''
    try:
        tuple = parsedate_tz(data)
        if not tuple:
            return None
        tz = tuple[-1]
        if tz is None:
            return datetime.datetime(*tuple[:6])
        return datetime.datetime(*tuple[:6],tzinfo=tzoffset(None,tz))
    except ValueError:
        return None

def seek_charset(msg):
    '''
    Try and derive non-ascii charset from message payload(s).
    Return None if none found.
    '''
    for part in msg.walk():
        charset = part.get_content_charset()
        if charset and charset not in ('ascii','us-ascii'):
            break
    if charset in ('ascii','us-ascii'):
        return None
    else:
        return charset
# --------------------------------------------------
# Classes
# --------------------------------------------------
class BetterMbox(mailbox.mbox):
    '''
    A better mbox class.  We are overriding the _generate_toc function to use a more restrictive
    From line check.  Based on the deprecated UnixMailbox.  Also, separator lines must be preceeded
    by a blank line.
    '''
    _fromlinepattern = (r'From (.*@.* |MAILER-DAEMON ).{24}')
    _regexp = None

    def _generate_toc(self):
        """Generate key-to-(start, stop) table of contents."""
        starts, stops = [], []
        lines = deque(' ',maxlen=2)
        self._file.seek(0)
        while True:
            line_pos = self._file.tell()
            lines.append(self._file.readline())
            if lines[1][:5] == 'From ' and self._isrealfromline(lines[1]) and not lines[0].strip():
                if len(stops) < len(starts):
                    stops.append(line_pos - len(os.linesep))
                starts.append(line_pos)
            elif lines[1] == '':
                stops.append(line_pos)
                break
        self._toc = dict(enumerate(zip(starts, stops)))
        self._next_key = len(self._toc)
        self._file_length = self._file.tell()

    def _strict_isrealfromline(self, line):
        if not self._regexp:
            import re
            self._regexp = re.compile(self._fromlinepattern)
        return self._regexp.match(line)

    _isrealfromline = _strict_isrealfromline

class CustomMbox(mailbox.mbox):
    '''
    Custom mbox class.  Designed to handle mbox-like files which do not have "From " envelope
    headers.  Keyword argument "separator" is required.  It is an RE object that is the pattern
    of the separator line.  ie. "^Envelope-to:".  Separator lines must be preceeded by a blank
    line.
    '''
    def __init__(self, *args, **kwargs):
        self._separator = kwargs.pop('separator')
        mailbox.mbox.__init__(self, *args, **kwargs)    # can't use super because mbox is old style class

    def _generate_toc(self):
        """Generate key-to-(start, stop) table of contents."""
        starts, stops = [], []
        lines = deque(' ',maxlen=2)
        self._file.seek(0)
        while True:
            line_pos = self._file.tell()
            lines.append(self._file.readline())
            if self._separator.match(lines[1]) and not lines[0].strip():
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
        start, stop = self._lookup(key)
        self._file.seek(start)
        from_line = self._file.readline().replace(os.linesep, '')
        if HEADER_PATTERN.match(from_line):
            self._file.seek(start)                      # reset pointer to keep first header line
        string = self._file.read(stop - self._file.tell())
        msg = self._message_factory(string.replace(os.linesep, '\n'))
        msg.set_from(from_line[5:])
        return msg

class Loader(object):
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

    def cleanup(self):
        '''
        Call this function when you are done with the loader object
        '''
        #logger.info('size: %s, loaded: %s' % (self.mb._file_length,self.stats['bytes_loaded']))
        self.mb.close()

    def load_message(self,msg):
        '''
        This function uses MessageWrapper to save a Message to the archive.  If we are in test
        mode the save() step is skipped.  If this is the firstrun of the import, we filter
        spam by checking that the message exists in the legacy web archive (which has been
        purged of spam) before saving.

        NOTE: if the message is from the last 30 days we skip this step, because there will be some
        lag between when the legacy archive index was created and the firstrun import completes.
        The check will also be skipped if msgid was not found in the original message and we
        had to create one, becasue it obviously won't exist in the web archive.
        '''
        self.stats['count'] += 1

        if not msg.items():         # no headers, something is wrong
            raise NoHeaders

        mw = MessageWrapper(msg, self.listname, private=self.private)

        # filter using Legacy archive
        if self.options.get('firstrun') and mw.date < (datetime.datetime.now() - datetime.timedelta(days=30)) and mw.created_id == False:
            legacy = Legacy.objects.filter(msgid=mw.msgid,email_list_id=self.listname)
            if not legacy:
                self.stats['spam'] += 1
                if not (self.options.get('dryrun') or self.options.get('test')):
                    mw.write_msg(subdir='spam')
                return

        # process message
        x = mw.archive_message
        self.stats['bytes_loaded'] += mw.bytes

        if not self.options.get('dryrun'):
            mw.save(test=self.options.get('test'))

    def process(self):
        '''
        If the "break" option is set propogate the exception
        '''
        for m in self.mb:
            try:
                self.load_message(m)
            except GenericWarning as error:
                logger.warn("Import Warn [{0}, {1}, {2}]".format(self.filename,error.args,m.get_from()))
            except Exception as error:
                if self.klass == 'BetterMbox':
                    identifier = m.get_from()
                else:
                    identifier = m.get('Message-ID','')
                log_msg = "Import Error [{0}, {1}, {2}]".format(self.filename,(error.__class__,error.args),identifier)
                logger.error(log_msg)
                self.save_failed_msg(m)
                self.stats['errors'] += 1
                if self.options.get('break'):
                    print log_msg
                    raise

        self.cleanup()

    def save_failed_msg(self,msg):
        mw = MessageWrapper(msg, self.listname, private=self.private)
        mw.write_msg(subdir='failed')

class MessageWrapper(object):
    '''
    This class takes a email.message.Message object (email_message) and listname as a string
    and constructs the mlarchive.archive.models.Message (archive_message) object.
    Use the save() method to save the message in the archive.

    Use lazy initialization.  On init only get message-id.  If this message is being filtered
    by message id, no use performing rest of message parsing.
    '''
    def __init__(self, email_message, listname, private=False):
        self._archive_message = None
        self._date = None
        self.created_id = False
        self.email_message = email_message
        self.hashcode = None
        self.listname = listname
        self.private = private
        self.spam_score = 0
        self.bytes = len(email_message.as_string(unixfrom=True))

        self.msgid = self.get_msgid()

    def _get_archive_message(self):
        "Returns the archive.models.Message instance"
        if self._archive_message is None:
            self.process()
        return self._archive_message
    archive_message = property(_get_archive_message)

    def _get_date(self):
        if not self._date:
            self._date = self.get_date()
        return self._date
    date = property(_get_date)

    @check_datetime
    def get_date(self):
        '''
        This function gets the message date.  It takes an email.Message object and returns a naive
        Datetime object in UTC time.

        First we inspect the Date: header field, since it should correspond with the date and
        time the message composer sent the email.  It also usually contains the timezone
        information which is important for calculating correct UTC.  Unfortunately the Date header
        can vary dramatically in format or even be missing.  Next we check for a Received header
        which should contain an RFC2822 date.  Lastly we check the envelope header, which should
        have an asctime date (no timezone info).
        '''
        fallback = None
        for func in (get_header_date,get_received_date,get_envelope_date):
            date = func(self.email_message)
            if date:
                if is_aware(date):
                    try:
                        return date.astimezone(pytz.utc).replace(tzinfo=None)   # return as naive UTC
                    except ValueError:
                        pass
                else:
                    fallback = date
            # if get_received_date fails could be spam or corrupt message, flag it
            elif func.__name__ == 'get_received_date':
                self.mark(MARK_BITS['NO_RECVD_DATE'])

        #logger.warn("Import Warn [{0}, {1}, {2}]".format(self.msgid,'Used None or naive date',
        #                                                 self.email_message.get_from()))

        if fallback:
            return fallback
        else:
            # can't really proceed without a date, this likely indicates bigger parsing error
            raise DateError("%s, %s" % (self.msgid,self.email_message.get_from()))

    def get_hash(self):
        '''
        Takes the msgid and returns the hashcode
        '''
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
            self.mark(MARK_BITS['NO_MSGID'])
            #raise GenericWarning('No MessageID (%s)' % self.email_message.get_from())
        return msgid

    def get_random_name(self, ext):
        '''
        This function generates a randomized filename for storing attachments.  It takes the
        file extension as a string and builds a name like extXXXXXXXXXX.ext, where X is a random
        letter digit or underscore, and ext is the file extension.
        '''
        chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + '_'
        rand = ''.join(random.choice(chars) for x in range(10))
        return '%s%s.%s' % (ext, rand, ext)

    def get_subject(self):
        '''
        This function gets the message subject.  If the subject looks like spam, long line with
        no spaces, truncate it so as not to cause index errors
        '''
        subject = self.normalize(self.email_message.get('Subject',''))
        # TODO: spam?
        #if len(subject) > 120 and len(subject.split()) == 1:
        #    subject = subject[:120]
        return subject

    def get_to(self):
        '''
        Use utility functions to extract RFC2822 addresses.  Returns a string with space
        deliminated addresses and names.
        '''
        to = self.email_message.get('to')
        if not to:
            return ''
        result = []
        addrs = getaddresses([decode_rfc2047_header(to)])   # getaddresses takes a sequence
        # flatten list of tuples
        for tuple in addrs:
            result = result + list(tuple)

        return ' '.join(result)

    def get_thread(self):
        '''
        This is a simplified version of the Zawinski threading algorithm.  The process is:
        1) If there are References, lookup the first message-id in the list and return it's thread.
           If the message isn't found try the next message-id, repeat.  According to RFC1036
           the references list is ordered oldest first.  To start searching from the nearest
           thread sibling reverse the list.
        2) If 'In-Reply-To-' is set, look up that message and return it's thread id.
        3) If the subject line has a "Re:" prefix look for the message matching base-subject
           and return it's thread
        4) If none of the above, return a new thread id

        Messages must be loaded in chronological order for this to work properly.

        Referecnces:
        - http://www.jwz.org/doc/threading.html
        - http://tools.ietf.org/html/rfc5256
        '''
        # TODO: one option is to leave these fields off the model instance

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
        return Thread.objects.create()

    def normalize(self, header_text, default='latin-1'):
        '''
        This function takes some header_text as a string.
        It returns the string decoded and normalized.
        Checks if the header needs decoding:
        - if text contains encoded_words, "=?", use decode_rfc2047_header()
        - default to latin-1, replace
        - finally, compress whitespace characters to one space
        '''
        if not header_text:                  # just return if we are passed an empty string
            return header_text

        # TODO: need this?
        #if type(header_text) is unicode:    # return if already unicode
        #    return header_text              # ie. get_filename() for example sometimes returns unicode

        if '=?' in header_text:              # handle RFC2047 encoded-words
            normal = decode_rfc2047_header(header_text)

        else:
            try:                             # if it's pure ascii we're done
                normal = unicode(header_text,'ascii')
            except (UnicodeDecodeError, UnicodeEncodeError):
                normal = unicode(header_text,default,errors='replace')
                self.mark(MARK_BITS['NON_ASCII_HEADER'])      # mark as possible spam


        # TODO: refactor with get_charsets(), or simply remove
        #charset = seek_charset(msg)
        #if charset:
        #    try:
        #        return unicode(header_text,charset)
        #    except (UnicodeDecodeError, LookupError):
        #        pass

        # encode as UTF8 and compress whitespace
        normal = normal.encode('utf8')
        normal = clean_spaces(normal)
        return normal.rstrip()

    def process(self):
        '''
        Perform the rest of the parsing and construct the Message object.  Note, we are not
        saving the object to the database.  This happens in the save() function.
        '''
        self.email_list,created = EmailList.objects.get_or_create(
            name=self.listname,defaults={'description':self.listname,'private':self.private})
        self.hashcode = self.get_hash()
        self.in_reply_to = self.email_message.get('In-Reply-To','')
        self.references = self.email_message.get('References','')
        self.subject = self.get_subject()
        self.base_subject = get_base_subject(self.subject)
        self.thread = self.get_thread()

        self._archive_message = Message(date=self.date,
                             email_list=self.email_list,
                             frm = self.normalize(self.email_message.get('From','')),
                             hashcode=self.hashcode,
                             in_reply_to=self.in_reply_to,
                             msgid=self.msgid,
                             subject=self.subject,
                             references=self.references,
                             base_subject=self.base_subject,
                             spam_score=self.spam_score,
                             thread=self.thread,
                             to=self.get_to())
        # not saving here.

    def process_attachments(self, test=False):
        '''
        This function walks the message parts and saves any attachments
        '''
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
                    for i in range(10):     # try up to ten random filenames
                        filename = self.get_random_name(extension)
                        path = os.path.join(self.archive_message.get_attachment_path(),filename)
                        if not os.path.exists(path):
                            with open(path, 'wb') as f:
                                f.write(payload)
                                attach.filename = filename
                                attach.save()
                            break
                        else:
                            logger.error("ERROR: couldn't pick unique attachment name in ten tries (list:%s)" % (self.listname))

    def save(self, test=False):
        '''
        Ensure message is not duplicate message-id or hash.  Save message to database.  Save
        to disk (if not test mode) and process attachments.
        '''
        # ensure process has been run
        # self._get_archive_message()

        # check for duplicate message id, and skip
        if Message.objects.filter(msgid=self.msgid,email_list__name=self.listname):
            raise GenericWarning('Duplicate msgid: %s' % self.msgid)

        # check for duplicate hash
        if Message.objects.filter(hashcode=self.hashcode):
            # TODO different error?
            raise CommandError('Duplicate hash, msgid: %s' % self.msgid)

        self.archive_message.save()     # save to database
        if not test:
            self.write_msg()            # write to disk archive

        # now that the archive.Message object is created we can process any attachments
        self.process_attachments(test=test)

    def write_msg(self,subdir=None):
        '''
        Write a copy of the original email message to the disk archive.
        Use optional argument subdir to specify a special location,
        ie. "spam" or "failure" subdirectory.
        '''
        filename = self.hashcode
        if not filename:
            filename = str(uuid.uuid4())

        if subdir:
            path = os.path.join(settings.ARCHIVE_DIR,subdir,self.listname,filename)
        else:
            path = os.path.join(settings.ARCHIVE_DIR,self.listname,filename)
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path,'w') as f:
            f.write(self.email_message.as_string(unixfrom=True))