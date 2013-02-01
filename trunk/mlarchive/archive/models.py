from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string
from bs4 import BeautifulSoup
from HTMLParser import HTMLParser, HTMLParseError
from html2text import html2text

import logging
import mailbox
import os

US_CHARSETS = ('us-ascii','iso-8859-1')
OTHER_CHARSETS = ('gb2312',)
UNSUPPORTED_CHARSETS = ('unknown',)

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
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

@skip_attachment
def handle_plain(part,text_only):
    # get_charset() doesn't work??
    if part.get_content_charset():
        charset = part.get_content_charset()
    elif part.get_param('charset'):
        charset = part.get_param('charset').lower()
    else:
        charset = US_CHARSETS[0]
    
    payload = part.get_payload(decode=True)
    #if charset not in US_CHARSETS and charset not in UNSUPPORTED_CHARSETS:
        # TODO log failure and pass
        #try:
        #payload = payload.decode(charset)
        #except UnicodeDecodeError:
    #return render_to_string('archive/message_plain.html', {'payload': payload})
    return payload
    
@skip_attachment
def handle_html(part,text_only):
    if not text_only:
        return render_to_string('archive/message_html.html', {'payload': part.get_payload(decode=True)})
    else:
        payload = part.get_payload(decode=True)
        uni = unicode(payload,errors='ignore')
        
        # tried many solutions here
        # text = strip_tags(part.get_payload(decode=True)) # problems with bad html 
        # soup = BeautifulSoup(part.get_payload(decode=True)) # errors with lxml 
        soup = BeautifulSoup(part.get_payload(decode=True),'html5') # included "html" and css
        text = soup.get_text()
        # text = html2text(uni) # errors with malformed tags
        return text
        
# a dictionary of supported mime types
HANDLERS = {'text/plain':handle_plain,
            'text/html':handle_html}

def handle(part,text_only):
    #return chunk.get_content_type()
    type = part.get_content_type()
    handler = HANDLERS.get(type,None)
    if handler:
        return handler(part,text_only)
    
def parse(entity, text_only=False):
    '''
    This function recursively traverses a MIME email and returns it's parts.
    The function takes an email.message object, 
    '''
    #print "calling parse %s:%s" % (entity.__class__,entity.get_content_type())
    parts = []
    if entity.is_multipart():
        if entity.get_content_type() == 'multipart/alternative':
            contents = entity.get_payload()
            # if output is not for indexing start from the most detailed option
            if not text_only:
                contents = contents[::-1]
            #print "first alt: %s" % contents[0].get_content_type()
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
"""
OLD FUNCTIONS -------------------------------

def parse(path):
    '''
    Parse message mime parts
    '''
    parts = []
    alt_count = 0
    try:
        with open(path) as f:
            maildirmessage = mailbox.MaildirMessage(f)
            headers = maildirmessage.items()
            for part in maildirmessage.walk():
                type = part.get_content_type()
                if type == 'multipart/alternative':
                    alt_count = len(part.get_payload())
                    continue
                handler = HANDLERS.get(type,None)
                if handler:
                    parts.append(handler(part))
    
    except IOError, e:
        return ''
        
    return parts

def parse_body(msg,html=False,request=None):
    '''
    This function takes a Message object and returns the message body.
    Option arguments: 
    html: if true format with HTML for display in templates, if false return text only, good
    for indexing.
    request: a request object to use in building links for HTML
    '''
    try:
        with open(msg.get_file_path()) as f:
            maildirmessage = mailbox.MaildirMessage(f)
            headers = maildirmessage.items()
            parts = []
            for part in maildirmessage.walk():
                if part.get_content_maintype() == 'multipart':
                    continue    # TODO do something with this
                handler = HANDLERS.get(part.get_content_type(),None)
                if handler:
                    parts.append(handler(part,html))
    except IOError, e:
        return 'ERROR: reading message'
    
    if html:
        return render_to_string('archive/message.html', {
            'msg': msg,
            'maildirmessage': maildirmessage,
            'headers': headers,
            'parts': parts,
            'request': request}
        )
    else:
        return '\n'.join(parts)
"""
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
    cc = models.CharField(max_length=255,blank=True)
    date = models.DateTimeField(db_index=True)
    email_list = models.ForeignKey(EmailList,db_index=True)
    frm = models.CharField(max_length=255,db_index=True)
    hashcode = models.CharField(max_length=28,db_index=True)
    headers = models.TextField()
    inrt = models.CharField(max_length=255,blank=True)      # in-reply-to header field
    legacy_number = models.IntegerField(blank=True,null=True,db_index=True)  # for mapping mhonarc
    msgid = models.CharField(max_length=255,db_index=True)
    references = models.ManyToManyField('self',through='Reference',symmetrical=False)
    subject = models.CharField(max_length=255)
    thread = models.ForeignKey(Thread)
    to = models.CharField(max_length=255,blank=True,default='')
    
    def __unicode__(self):
        return self.msgid

    def get_absolute_url(self):
        pass
    
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

    