from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string

import logging
import mailbox
import os

US_CHARSETS = ('us-ascii','iso-8859-1')
OTHER_CHARSETS = ('gb2312')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def handle_plain(part):
    # get_charset() doesn't work??
    charset = part.get_param('charset').lower()
    payload = part.get_payload(decode=True)
    if charset not in US_CHARSETS:
        # TODO log failure and pass
        #try:
        payload = payload.decode(charset)
        #except UnicodeDecodeError:
    return render_to_string('archive/message_plain.html', {'payload': payload})
    
def handle_html(part):
    return render_to_string('archive/message_html.html', {'payload': part.get_payload(decode=True)})
    
# a dictionary of supported mime types
HANDLERS = {'text/plain':handle_plain,
            'text/html':handle_html}
            
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
    
    @property
    def body(self):
        try:
            with open(self.get_file_path()) as f:
                return f.read()
        except IOError, e:
            #logger = logging.getLogger(__name__)
            #logger.warning('IOError %s' % e)
            # TODO: handle this better
            return ''
        
    @property
    def html(self):
        '''
        Return HTML representation of the message.  The MaildirMessage object simulates
        a dictionary.  As a result it's methods are not available to the Django template.
        Therefore we need to pass these to the template individually.
        '''
        try:
            with open(self.get_file_path()) as f:
                maildirmessage = mailbox.MaildirMessage(f)
                headers = maildirmessage.items()
                parts = []
                for part in maildirmessage.walk():
                    handler = HANDLERS.get(part.get_content_type(),None)
                    if handler:
                        parts.append(handler(part))
        except IOError, e:
            return ''
            
        return render_to_string('archive/message.html', {
            'msg': self,
            'maildirmessage': maildirmessage,
            'headers': headers,
            'parts': parts}
        )
    
    def __unicode__(self):
        return self.msgid

    def get_absolute_url(self):
        pass
    
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

    