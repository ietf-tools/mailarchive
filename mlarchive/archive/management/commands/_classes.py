from django.conf import settings
from django.core.management.base import CommandError
from dateutil.tz import tzoffset
from email.utils import parsedate, parsedate_tz, mktime_tz
from mlarchive.archive.models import *
from tzparse import tzparse

import base64
import datetime
import hashlib
import mailbox
import os
import pytz
import re
import time

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
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
    
class loader(object):
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
        
        self.email_list,created = EmailList.objects.get_or_create(
            name=self.listname,defaults={'description':self.listname,'private':self.private})
        
    def cleanup(self):
        '''
        Call this function when you are done with the loader object
        '''
        self.mb.close()
        
    def elapsedtime(self):
        return self.endtime - self.starttime
        
    def get_date(self,msg):
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
            date = func(msg)
            if date:
                if is_aware(date):
                    try:
                        return date.astimezone(pytz.utc).replace(tzinfo=None)   # return as naive UTC
                    except ValueError:
                        pass
                else:
                    fallback = date
        logger.warn("Import Warn [{0}, {1}, {2}]".format(self.filename,'Used None or naive date',msg.get_from()))
        return fallback
            
    def get_hash(self,msgid):
        '''
        Takes the name of the email list and msgid and returns the hashcode
        '''
        sha = hashlib.sha1(msgid)
        sha.update(self.listname)
        return base64.urlsafe_b64encode(sha.digest())
        
    def get_stats(self):
        '''
        Return statistics from the process() function
        '''
        return "%s:%s:%s:%s:%.3f\n" % (self.listname,os.path.basename(self.filename),
                                     self.stats['count'],self.stats['errors'],self.elapsedtime())
    def get_subject(self,msg):
        '''
        This function gets the message subject.  If the subject looks like spam, long line with
        no spaces, truncate it so as not to cause index errors
        '''
        subject = handle_header(msg.get('Subject',''))
        if len(subject) > 120 and len(subject.split()) == 1:
            subject = subject[:120]
        return subject
        
    def get_thread(self,msg):
        '''
        This is a very basic thread algorithm.  If 'In-Reply-To-' is set, look up that message 
        and return it's thread id, otherwise return a new thread id.  This is crude for many reasons.
        ie. what if the referenced message isn't loaded yet?  We load message files in date order
        to minimize this.
        see http://www.jwz.org/doc/threading.html
        '''
        irt = msg.get('In-Reply-To','').strip('<>')
        if irt:
            self.stats['irts'] += 1
            try:
                irt_msg = Message.objects.get(msgid=irt)
                thread = irt_msg.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                self.stats['mirts'] += 1
                thread = Thread.objects.create()
        else:
            thread = Thread.objects.create()
        return thread
    
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
        
    def load_message(self,m):
        '''
        This function takes an email.Message object and creates the archive.Message object
        '''
        self.stats['count'] += 1
        
        # handle message-id ========================
        msgid = handle_header(m.get('Message-ID',''))
        if msgid:
            msgid = msgid.strip('<>')
        else:
            # see if this is a resent Message, which sometimes have missing Message-ID field
            resent_msgid = m.get('Resent-Message-ID')
            if resent_msgid:
                msgid = resent_msgid.strip('<>')
        if not msgid:
            raise GenericWarning('No MessageID (%s)' % m.get_from())
            
        hashcode = self.get_hash(msgid)
        # filter against legacy archive
        try: 
            legacy = Legacy.objects.get(msgid=msgid,email_list_id=self.email_list.name)
        except Legacy.DoesNotExist:
            #raise GenericWarning('Not in legacy DB (spam?): %s' % msgid)
            self.write_msg(m,hashcode,spam=True)
            self.stats['spam'] += 1
            return None
        
        # check for duplicate message id, and skip
        if Message.objects.filter(msgid=msgid,email_list=self.email_list):
            raise GenericWarning('Duplicate msgid: %s' % msgid)
            
        # check for duplicate hash
        if Message.objects.filter(hashcode=hashcode):
            raise CommandError('Duplicate hash, msgid: %s' % msgid)
        
        inrt = m.get('In-Reply-To','')
        if inrt:
            inrt = inrt.strip('<>')
            
        msg = Message(date=self.get_date(m),
                      email_list=self.email_list,
                      frm = handle_header(m.get('From','')),
                      hashcode=hashcode,
                      inrt=inrt,
                      msgid=msgid,
                      subject=self.get_subject(m),
                      thread=self.get_thread(m),
                      to=handle_header(m.get('To','')))
        msg.save()
        self.write_msg(m,hashcode)
        
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
    
    def write_msg(self,m,hashcode,spam=False):
        '''
        This function takes an email.Message object and writes a copy of it to the disk archive
        '''
        if self.options.get('test'):
            return None
        if spam:
            path = os.path.join(settings.ARCHIVE_DIR,'spam',self.email_list.name,hashcode)
        else:
            path = os.path.join(settings.ARCHIVE_DIR,self.email_list.name,hashcode)
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path,'w') as f:
            f.write(m.as_string())
        
        # Suppress database warnings
        #from warnings import filterwarnings
        #filterwarnings('ignore', category = MySQLdb.Warning)
