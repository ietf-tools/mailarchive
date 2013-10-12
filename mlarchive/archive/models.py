from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.template.loader import render_to_string

from email.utils import parseaddr, collapse_rfc2231_value
from email.Header import decode_header

from bs4 import BeautifulSoup
from HTMLParser import HTMLParser, HTMLParseError
#from html2text import html2text
from mlarchive.archive.generator import Generator

import mailbox
import os
import shutil

US_CHARSETS = ('us-ascii','ascii')
DEFAULT_CHARSET = 'us-ascii'
OTHER_CHARSETS = ('gb2312',)
UNSUPPORTED_CHARSETS = ('unknown','x-unknown')

TXT2HTML = ['/usr/bin/mhonarc','-single']

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


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
    members_digest = models.CharField(max_length=28,blank=True)

    def __unicode__(self):
        return self.name

class Message(models.Model):
    cc = models.TextField(blank=True,default='')
    date = models.DateTimeField(db_index=True)
    email_list = models.ForeignKey(EmailList,db_index=True)
    frm = models.CharField(max_length=125,db_index=True)    # really long from lines are spam
    hashcode = models.CharField(max_length=28,db_index=True)
    #inrt = models.CharField(max_length=1024,blank=True)     # in-reply-to header field
    legacy_number = models.IntegerField(blank=True,null=True,db_index=True)  # for mapping mhonarc
    msgid = models.CharField(max_length=255,db_index=True)
    #references = models.ManyToManyField('self',through='Reference',symmetrical=False)
    spam_score = models.IntegerField(default=0)             # >0 = spam
    subject = models.CharField(max_length=512,blank=True)
    thread = models.ForeignKey(Thread)
    to = models.TextField(blank=True,default='')
    updated = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.msgid

    def as_html(self):
        '''
        A method that returns the message formated as HTML.  Uses MHonarc standalone
        '''
        with open(self.get_file_path) as f:
            mhout = subprocess.check_output(TXT2HTML,stdin=f)
        soup = BeautifulSoup(mhout)
        return soup.body

    def get_absolute_url(self):
        return '/archive/detail/%s/%s' % (self.email_list.name,self.hashcode)

    def get_attachment_path(self):
        path = os.path.join(settings.ARCHIVE_DIR,self.email_list.name,'attachments')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_body(self):
        '''
        Returns the contents of the message body, text only for use in indexing.
        ie. HTML is stripped.
        '''
        gen = Generator(self)
        return gen.as_text()

    def get_body_html(self, request=None):
        gen = Generator(self)
        return gen.as_html(request=request)

    def get_body_raw(self):
        '''
        Utility function.  Returns the raw contents of the message file.
        NOTE: this will include encoded attachments
        '''
        try:
            with open(self.get_file_path()) as f:
                return f.read()
        except IOError as error:
            #logger.warning('IOError %s' % error)
            # TODO: handle this better
            return 'Error: message not found.'

    def get_file_path(self):
        return os.path.join(settings.ARCHIVE_DIR,self.email_list.name,self.hashcode)

    def export(self):
        '''export this message'''
        pass

    @property
    def friendly_frm(self):
        pass

    @property
    def frm_email(self):
        '''
        This property is the email portion of the "From" header all lowercase (the realname
        is stripped).  It is used in faceting search results as well as display.
        '''
        return parseaddr(self.frm)[1].lower()

class Attachment(models.Model):
    error = models.CharField(max_length=255,blank=True) # message if problem with attachment
    description = models.CharField(max_length=255)      # description of file contents
    filename = models.CharField(max_length=255)         # randomized archive filename
    message = models.ForeignKey(Message)
    name = models.CharField(max_length=255)             # regular name of attachment

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        path = os.path.join('/',self.message.email_list.name,'attachments',self.filename)
        return path

    def get_file_path():
        dir = os.path.dirname(self.message.get_file_path())
        path = os.path.join(dir,'attachments',self.filename)
        return path

class Legacy(models.Model):
    email_list_id = models.CharField(max_length=40)
    msgid = models.CharField(max_length=255,db_index=True)
    number = models.IntegerField()

    def __unicode__(self):
        return '%s:%s' % (self.email_list_id,self.msgid)

# Signal Handlers ----------------------------------------

@receiver(pre_delete, sender=Message)
def _message_remove(sender, instance, **kwargs):
    '''
    When messages are removed, via the admin page, we need to move the message
    archive file to the "removed" directory
    '''
    path = instance.get_file_path()
    if not os.path.exists(path):
        return
    target = os.path.join(os.path.dirname(path),'removed')
    if not os.path.exists(target):
        os.mkdir(target)
    shutil.move(path,target)

