from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string

from email.utils import parseaddr, collapse_rfc2231_value
from email.Header import decode_header

from bs4 import BeautifulSoup
from HTMLParser import HTMLParser, HTMLParseError
#from html2text import html2text

import mailbox
import os

US_CHARSETS = ('us-ascii','ascii')
DEFAULT_CHARSET = 'ascii'
OTHER_CHARSETS = ('gb2312',)
UNSUPPORTED_CHARSETS = ('unknown','x-unknown')

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def get_charset(part):
    # part.get_charset() doesn't work??
    if part.get_content_charset():
        charset = part.get_content_charset()
    elif part.get_param('charset'):
        charset = part.get_param('charset').lower()
    else:
        charset = US_CHARSETS[0]
    return charset
    
def handle_header(header_text, default="ascii"):
    """Decode header_text if needed"""
    try:
        headers=decode_header(header_text)
    except email.Errors.HeaderParseError:
        # This already append in email.base64mime.decode()
        # instead return a sanitized ascii string 
        return header_text.encode('ascii', 'replace').decode('ascii')
    else:
        for i, (text, charset) in enumerate(headers):
            try:
                headers[i]=unicode(text, charset or default, errors='replace')
            except LookupError:
                # if the charset is unknown, force default 
                headers[i]=unicode(text, default, errors='replace')
        return u"".join(headers)
        
def skip_attachment(function):
    '''
    This is a decorator for custom MIME part handlers, handle_*.  
    If the part passed is an attachment then it is skipped (None is returned).
    '''
    def _inner(*args, **kwargs):
        if args[0].get_filename():
            return None
        return function(*args, **kwargs)
    return _inner
    
class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

def handle_external_body(part,text_only):
    '''
    Two common formats:
    A) in content type parameters
    Content-Type: Message/External-body; name="draft-ietf-alto-reqs-03.txt";
        site="ftp.ietf.org"; access-type="anon-ftp";
        directory="internet-drafts"

    Content-Type: text/plain
    Content-ID: <2010-02-17021922.I-D@ietf.org>

    B) as an attachment
    Content-Type: message/external-body; name="draft-howlett-radsec-knp-01.url"
    Content-Description: draft-howlett-radsec-knp-01.url
    Content-Disposition: attachment; filename="draft-howlett-radsec-knp-01.url";
        size=92; creation-date="Mon, 14 Mar 2011 22:39:25 GMT";
        modification-date="Mon, 14 Mar 2011 22:39:25 GMT"
    Content-Transfer-Encoding: base64
    
    W0ludGVybmV0U2hvcnRjdXRdDQpVUkw9ZnRwOi8vZnRwLmlldGYub3JnL2ludGVybmV0LWRyYWZ0
    cy9kcmFmdC1ob3dsZXR0LXJhZHNlYy1rbnAtMDEudHh0DQo=
    '''
    if text_only:
        return None
    
    # handle B format
    if part.get_filename() and part.get_filename().endswith('url'):
        codec = part['Content-Transfer-Encoding']
        inner = part.get_payload()
        payload = inner[0].get_payload()
        link = payload.decode(codec)
        return link
    # handle A format
    else:
        rawsite = part.get_param('site')
        site = collapse_rfc2231_value(rawsite)
        rawdir = part.get_param('directory')
        dir = collapse_rfc2231_value(rawdir)
        rawname = part.get_param('name')
        name = collapse_rfc2231_value(rawname)
        link = 'ftp://%s/%s/%s' % (site,dir,name)
        html = '<div><a rel="nofollow" href="%s">&lt;%s&gt;</a></div>' % (link,link)
        return html

@skip_attachment
def handle_html(part,text_only):
    if not text_only:
        payload = part.get_payload(decode=True)
        charset = part.get_content_charset()
        uni = unicode(payload,charset or DEFAULT_CHARSET,errors='replace')
        return render_to_string('archive/message_html.html', {'payload': uni})
    else:
        payload = part.get_payload(decode=True)
        uni = unicode(payload,errors='ignore')
        # tried many solutions here
        # text = strip_tags(part.get_payload(decode=True)) # problems with bad html 
        # soup = BeautifulSoup(part.get_payload(decode=True)) # errors with lxml 
        # text = html2text(uni) # errors with malformed tags
        soup = BeautifulSoup(part.get_payload(decode=True),'html5') # included "html" and css
        text = soup.get_text()
        
        return text
        
@skip_attachment
def handle_plain(part,text_only):
    charset = get_charset(part)
    payload = part.get_payload(decode=True)
    if charset not in US_CHARSETS and charset not in UNSUPPORTED_CHARSETS:
        try:
            payload = payload.decode(charset)
        except UnicodeDecodeError as err:
            logger.warn("UnicodeDecodeError [{0}, {1}]".format(err.encoding,err.reason))
            payload = unicode(payload,DEFAULT_CHARSET,errors='ignore')
        except LookupError as err:
            logger.warn("Decode Error [{0}, {1}]".format(err.args,err.message))
            payload = unicode(payload,DEFAULT_CHARSET,errors='ignore')
            
    result = render_to_string('archive/message_plain.html', {'payload': payload})
    # undeclared charactersets can cause problems with template rendering
    # if result is empty template (len=28) try again with unicode
    if len(result) == 28 and not isinstance(payload, unicode):
        payload = unicode(payload,DEFAULT_CHARSET,errors='ignore')
        result = render_to_string('archive/message_plain.html', {'payload': payload})
    return result
    
# a dictionary of supported mime types
HANDLERS = {'message/external-body':handle_external_body,
            'text/plain':handle_plain,
            'text/html':handle_html}

def handle(part,text_only):
    type = part.get_content_type()
    #logger.debug('handling %s' % type)
    handler = HANDLERS.get(type,None)
    if handler:
        return handler(part,text_only)
    
def parse(entity, text_only=False):
    '''
    This function recursively traverses a MIME email and returns a list of email.Message objects
    '''
    #print "calling parse %s:%s" % (entity.__class__,entity.get_content_type())
    parts = []
    # messages with type message/external-body are marked multipart, but we need to treat them 
    # otherwise
    if entity.is_multipart() and entity.get_content_type() != 'message/external-body':
        if entity.get_content_type() == 'multipart/alternative':
            contents = entity.get_payload()
            # NOTE: rather than trying to handle possibly malformed HTML, just use the
            # text/plain versions for display.
            # --clip
            # if output is not for indexing start from the most detailed option
            # if not text_only:
            #     contents = contents[::-1]
            # --clip
            for x in contents:
                # only return first readable item
                r = parse(x,text_only)
                if r:
                    parts.extend(r)
                    break
        else:
            for part in entity.get_payload():
                parts.extend(parse(part,text_only))
    else:
        body = handle(entity,text_only)
        if body:
            parts.append(body)
    
    #print "returning parse %s:%s" % (type(parts),parts)
    return parts
    
def parse_body(msg, text_only=False, request=None):
    try:
        with open(msg.get_file_path()) as f:
            mm = mailbox.MaildirMessage(f)
            headers = mm.items()
            parts = parse(mm,text_only)
    except IOError:
        return 'Error reading message'
        
    if not text_only:
        return render_to_string('archive/message.html', {
            'msg': msg,
            'maildirmessage': mm,
            'headers': headers,
            'parts': parts,
            'request': request}
        )
    else:
        return '\n'.join(parts)

# --------------------------------------------------
# Models
# --------------------------------------------------

class Thread(models.Model):
    
    def __unicode__(self):
        return str(self.id)
    
class EmailList(models.Model):
    active = models.BooleanField(default=True,db_index=True)
    date_created = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255,blank=True)
    name = models.CharField(max_length=255,db_index=True,unique=True)
    private = models.BooleanField(default=False,db_index=True)
    alias = models.CharField(max_length=255,blank=True)
    members = models.ManyToManyField(User)

    def __unicode__(self):
        return self.name
    
class Message(models.Model):
    cc = models.TextField(blank=True,default='')
    date = models.DateTimeField(db_index=True)
    email_list = models.ForeignKey(EmailList,db_index=True)
    frm = models.CharField(max_length=255,db_index=True)    # both realname and email for search
    hashcode = models.CharField(max_length=28,db_index=True)
    inrt = models.CharField(max_length=1024,blank=True)     # in-reply-to header field
    legacy_number = models.IntegerField(blank=True,null=True,db_index=True)  # for mapping mhonarc
    msgid = models.CharField(max_length=255,db_index=True)
    references = models.ManyToManyField('self',through='Reference',symmetrical=False)
    subject = models.CharField(max_length=512,blank=True)
    thread = models.ForeignKey(Thread)
    to = models.TextField(blank=True,default='')
    
    def __unicode__(self):
        return self.msgid

    def get_absolute_url(self):
        return '/archive/detail/%s/%s' % (self.email_list.name,self.hashcode)
    
    def get_body(self):
        '''
        Returns the contents of the message body, text only for use in indexing.
        ie. HTML is stripped.
        '''
        return parse_body(self, text_only=True)
        
    def get_body_html(self, request=None):
        return parse_body(self, request=request)
        
    def get_body_raw(self):
        '''
        Utility function.  Returns the raw contents of the message file.
        NOTE: this will include encoded attachments
        '''
        try:
            with open(self.get_file_path()) as f:
                return f.read()
        except IOError, e:
            #logger = logging.getLogger(__name__)
            #logger.warning('IOError %s' % e)
            # TODO: handle this better
            return 'Error: message not found.'
            
    def get_file_path(self):
        return os.path.join(settings.ARCHIVE_DIR,self.email_list.name,self.hashcode)
        
    def export(self):
        '''export this message'''
        pass

    @property
    def friendly_frm(self):
        #TODO use safer method 
        parts = self.frm.split()
        if len(parts) >= 3 and parts[1] == 'at':
            return '%s@%s' % (parts[0],parts[2])
        else:
            part = [p for p in parts if '@' in p]
            return part[0].strip('<>')
    
    @property
    def frm_email(self):
        '''
        This property is the email portion of the "From" header all lowercase (the realname
        is stripped).  It is used in faceting search results as well as display.
        '''
        return parseaddr(self.frm)[1].lower()
        
class Attachment(models.Model):
    name = models.CharField(max_length=255)
    message = models.ForeignKey(Message)
    
    def __unicode__(self):
        return self.name
        
    def get_absolute_url(self):
        pass
        
    def get_file_path():
        pass
        
class Reference(models.Model):
    source_message = models.ForeignKey(Message,related_name='ref_source_set')
    target_message = models.ForeignKey(Message,related_name='ref_target_set')
    order = models.IntegerField()
    
    class Meta:
        ordering = ('order',)

