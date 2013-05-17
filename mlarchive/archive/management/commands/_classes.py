from django.conf import settings
from django.core.management.base import CommandError
from dateutil.tz import tzoffset
from email.utils import parsedate, parsedate_tz, mktime_tz, getaddresses
from mlarchive.archive.models import *
from tzparse import tzparse

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

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# Suppress database warnings
#from warnings import filterwarnings
#filterwarnings('ignore', category = MySQLdb.Warning)
        
# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def archive_message(msg,listname,private=False):
    mw = MessageWrapper(msg,listname,private=private)
    mw.save()
    
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

def get_header_date(msg):
    '''
    This function takes a email.Message object and tries to parse the date from the Date: header
    field.  It returns a Datetime object, either naive or aware, if it can, otherwise None.
    '''
    date = msg.get('date')
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

def get_envelope_date(msg):
    line = msg.get_from()
    if not line:
        return None
        
    if '@' in line:
        return parsedate_to_datetime(' '.join(line.split()[1:]))
    elif parsedate_to_datetime(line):    # sometimes Date: is first line of MMDF message
        return parsedate_to_datetime(line)

def get_received_date(msg):
    rec = msg.get('received')
    if not rec:
        return None
    
    parts = rec.split(';')
    return parsedate_to_datetime(parts[1])

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
# --------------------------------------------------
# Classes
# --------------------------------------------------
class CustomMbox(mailbox.mbox):
    '''
    Custom mbox class.  We are overriding the _generate_toc function to use a more restrictive
    From line check.  Base on the deprecated UnixMailbox
    '''
    _fromlinepattern = (r'From (.*@.* |MAILER-DAEMON ).{24}')
    _regexp = None
    
    def _generate_toc(self):
        """Generate key-to-(start, stop) table of contents."""
        starts, stops = [], []
        self._file.seek(0)
        while True:
            line_pos = self._file.tell()
            line = self._file.readline()
            if line[:5] == 'From ' and self._isrealfromline(line):
                if len(stops) < len(starts):
                    stops.append(line_pos - len(os.linesep))
                starts.append(line_pos)
            elif line == '':
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
    
class ListError(Exception):
    pass
    
class GenericWarning(Exception):
    pass
    
class DateError(Exception):
    pass

class Loader(object):
    def __init__(self, filename, **options):
        self.endtime = 0
        self.filename = filename
        self.options = options
        self.starttime = 0
        self.stats = {'irts': 0,'mirts': 0,'count': 0, 'errors': 0, 'spam': 0}
        self.listname = options.get('listname')
        self.private = options.get('private')
        # init mailbox iterator
        if self.options.get('format') == 'mmdf':
            self.mb = mailbox.MMDF(filename)
        else:
            #self.mb = mailbox.mbox(filename)   # TODO: handle different types of input files
            self.mb = CustomMbox(filename)
            
        if not self.listname:
            self.listname = self.guess_list()
        
        if not self.listname:
            raise ListError
            
        logger.info('loader called with: %s' % self.filename)
        
    def cleanup(self):
        '''
        Call this function when you are done with the loader object
        '''
        self.mb.close()
        
    def elapsedtime(self):
        return self.endtime - self.starttime
        
    def get_stats(self):
        '''
        Return statistics from the process() function
        '''
        return "%s:%s:%s:%s:%.3f\n" % (self.listname,os.path.basename(self.filename),
                                     self.stats['count'],self.stats['errors'],self.elapsedtime())
    
    def guess_list(self):
        '''
        Helper function to determine the list we are importing based on header values
        '''
        # not enought info in MMDF-style mailbox to guess list
        if isinstance(self.mb,mailbox.MMDF):
            return None
            
        if len(self.mb) == 0:
            return None
            
        msg = self.mb[0]
        if msg.get('X-BeenThere'):
            val = msg.get('X-BeenThere').split('@')[0]
            if val:
                return val
        if msg.get('List-Post'):
            val = msg.get('List-Post')
            match = re.match(r'<mailto:(.*)@.*',val)
            if match:
                return match.groups()[0]
        
    def load_message(self,msg):
        '''
        This function uses MessageWrapper to save a Message to the archive.  If we are in test
        mode the save() step is skipped.  If this is the firstrun of the import, we filter
        spam by checking that the message exists in the legacy web archive (which has been 
        purged of spam) before saving.  NOTE: if the message is from the last week we skip this
        step, because there will be some lag between when the legacy archive index was created
        and the firstrun import completes
        '''
        self.stats['count'] += 1
        mw = MessageWrapper(msg, self.listname, private=self.private)
        
        if self.options.get('test'):
            return
        
        if self.options.get('firstrun') and mw.get_date() < datetime.datetime.now() - datetime.timedelta(days=7):
            try: 
                legacy = Legacy.objects.get(msgid=mw.msgid,email_list_id=self.listname)
            except Legacy.DoesNotExist:
                self.stats['spam'] += 1
                return
        
        mw.save()
        
    def process(self):
        for m in self.mb:
            try:
                self.load_message(m)
            except GenericWarning as e:
                logger.warn("Import Warn [{0}, {1}, {2}]".format(self.filename,e.args,m.get_from()))
            except Exception as e:
                logger.error("Import Error [{0}, {1}, {2}]".format(self.filename,e.args,m.get_from()))
                self.stats['errors'] += 1
        self.cleanup()
        
    def startclock(self):
        self.starttime = time.time()
        
    def stopclock(self):
        self.endtime = time.time()

class MessageWrapper(object):
    '''
    This class takes a email.message.Message object (email_message) and constructs the 
    mlarchive.archive.models.Message (archive_message) object.  Use the save() method to save
    the message in the archive.
    '''
    def __init__(self, email_message, listname, private=False):
        self.email_message = email_message
        self.hashcode = None
        self.listname = listname
        self.private = private
        self.msgid = self.get_msgid()
        self._archive_message = None
        
    def _get_archive_message(self):
        "Returns the archive.models.Message instance"
        if self._archive_message is None:
            self.process()
        return self._archive_message
    archive_message = property(_get_archive_message)
    
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
        logger.warn("Import Warn [{0}, {1}, {2}]".format(self.filename,'Used None or naive date',
                                                         self.email_message.get_from()))
        return fallback
            
    def get_hash(self,msgid):
        '''
        Takes the msgid and returns the hashcode
        '''
        sha = hashlib.sha1(msgid)
        sha.update(self.listname)
        return base64.urlsafe_b64encode(sha.digest())
    
    def get_msgid(self):
        msgid = handle_header(self.email_message.get('Message-ID',''))
        if msgid:
            msgid = msgid.strip('<>')
        else:
            # see if this is a resent Message, which sometimes have missing Message-ID field
            resent_msgid = self.email_message.get('Resent-Message-ID')
            if resent_msgid:
                msgid = resent_msgid.strip('<>')
        if not msgid:
            raise GenericWarning('No MessageID (%s)' % self.email_message.get_from())
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
        subject = handle_header(self.email_message.get('Subject',''))
        if len(subject) > 120 and len(subject.split()) == 1:
            subject = subject[:120]
        return subject
    
    def get_to(self):
        '''
        Use utility functions to extract RFC2822 addresses.  Returns a string with space 
        deliminated addresses and names.
        '''
        #handle_header()
        result = []
        addrs = get_addresses(self.email_message.get_all('to',[]))
        # flatten list of tuples
        for tuple in addrs:
            result = result + list(tuple)
        
        return ' '.join(result)
        
    def get_thread(self):
        '''
        This is a very basic thread algorithm.  If 'In-Reply-To-' is set, look up that message 
        and return it's thread id, otherwise return a new thread id.  This is crude for many reasons.
        ie. what if the referenced message isn't loaded yet?  We load message files in date order
        to minimize this.
        see http://www.jwz.org/doc/threading.html
        '''
        irt = self.email_message.get('In-Reply-To','').strip('<>')
        if irt:
            #self.stats['irts'] += 1
            try:
                irt_msg = Message.objects.get(msgid=irt)
                thread = irt_msg.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                #self.stats['mirts'] += 1
                thread = Thread.objects.create()
        else:
            thread = Thread.objects.create()
        return thread
        
    def process(self):
        self.hashcode = self.get_hash(self.msgid)
        inrt = self.email_message.get('In-Reply-To','')
        if inrt:
            inrt = inrt.strip('<>')
        
        self.email_list,created = EmailList.objects.get_or_create(
            name=self.listname,defaults={'description':self.listname,'private':self.private})
            
        self._archive_message = Message(date=self.get_date(),
                             email_list=self.email_list,
                             frm = handle_header(self.email_message.get('From','')),
                             hashcode=self.hashcode,
                             inrt=inrt,
                             msgid=self.msgid,
                             subject=self.get_subject(),
                             thread=self.get_thread(),
                             to=self.get_to())
        
    def process_attachments(self):
        '''
        This function walks the message parts and saves any attachments
        '''
        for part in self.email_message.walk():
            # TODO can we have an attachment without a filename (content disposition) ??
            if part.get_filename():     # indicates an attachment
                type = part.get_content_type()
                if type in settings.SAFE_ATTACHMENT_TYPES:
                    filename = part.get_filename()
                    # convert invalid characters to underscores? mhmimetypes.pl
                    name, extension = os.path.splitext(filename)
                    # create record
                    Attachment.objects.create(message=self.archive_message,name=filename)
                    
                    # write to disk
                    for i in range(10):     # try up to ten random filenames
                        diskname = self.get_random_name(extension)
                        path = os.path.join(self.archive_message.get_attachment_path(),diskname)
                        if not os.path.exist(path):
                            with open(path, 'wb') as f:
                                f.write(part.get_payload(decode=True))
                            break
                        else:
                            logger.error("ERROR: couldn't pick unique attachment name in ten tries (list:%s)" % (self.listname))
                else:
                    logger.warn('WARN: unsafe attachment type not saved (msg:%s type:%s)' % (
                                self.msgid, type))
                                
    def save(self):
        # ensure process has been run
        self._get_archive_message()
        
        # check for duplicate message id, and skip
        if Message.objects.filter(msgid=self.msgid,email_list__name=self.listname):
            raise GenericWarning('Duplicate msgid: %s' % self.msgid)
            
        # check for duplicate hash
        if Message.objects.filter(hashcode=self.hashcode):
            # TODO different error?
            raise CommandError('Duplicate hash, msgid: %s' % self.msgid)
            
        self.archive_message.save()
        self.write_msg()
        
        # now that the archive.Message object is created we can process any attachments
        self.process_attachments()
        
    def write_msg(self,spam=False):
        '''
        This function writes a copy of the original email message to the disk archive
        '''
        if spam:
            path = os.path.join(settings.ARCHIVE_DIR,'spam',self.listname,self.hashcode)
        else:
            path = os.path.join(settings.ARCHIVE_DIR,self.listname,self.hashcode)
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path,'w') as f:
            f.write(self.email_message.as_string(unixfrom=True))