from django.db import models
from django.db.models.signals import pre_delete, post_delete, post_save
from django.dispatch.dispatcher import receiver
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db import models
from django.template.loader import render_to_string
from email.utils import parseaddr
from mlarchive.archive.generator import Generator

import os
import re
import shutil
import subprocess

TXT2HTML = ['/usr/bin/mhonarc','-single']
ATTACHMENT_PATTERN = r'<p><strong>Attachment:((?:.|\n)*?)</p>'

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')


# --------------------------------------------------
# Managers
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

    def get_failed_dir(self):
        return os.path.join(settings.ARCHIVE_DIR,'_failed',self.name)

    def get_removed_dir(self):
        return os.path.join(settings.ARCHIVE_DIR,self.name,'_removed')

class Message(models.Model):
    base_subject = models.CharField(max_length=512,blank=True)
    cc = models.TextField(blank=True,default='')
    date = models.DateTimeField(db_index=True)
    email_list = models.ForeignKey(EmailList,db_index=True)
    frm = models.CharField(max_length=125,db_index=True)    # really long from lines are spam
    hashcode = models.CharField(max_length=28,db_index=True)
    in_reply_to = models.CharField(max_length=1024,blank=True)     # in-reply-to header field
    legacy_number = models.IntegerField(blank=True,null=True,db_index=True)  # for mapping mhonarc
    msgid = models.CharField(max_length=255,db_index=True)
    references = models.TextField(blank=True,default='')
    spam_score = models.IntegerField(default=0)             # > 0 = spam
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
        with open(self.get_file_path()) as f:
            mhout = subprocess.check_output(TXT2HTML,stdin=f)

        # extract body
        within = False
        body = []
        for line in mhout.splitlines():
            if line == '<!--X-Body-of-Message-End-->':
                within = False
            if within:
                body.append(line)
            if line == '<!--X-Body-of-Message-->':
                within = True

        str = '\n'.join(body)

        # strip attachment links
        body = re.sub(ATTACHMENT_PATTERN,'',str)

        return body

    def get_absolute_url(self):
        # strip padding, "=", to shorten URL
        return reverse('archive_detail',kwargs={'list_name':self.email_list.name,
                                                'id':self.hashcode.rstrip('=')})

    def get_attachment_path(self):
        path = os.path.join(settings.ARCHIVE_DIR,self.email_list.name,'attachments')
        if not os.path.exists(path):
            os.makedirs(path)
            os.chmod(path,02777)
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

    def get_removed_dir(self):
        return os.path.join(settings.ARCHIVE_DIR,self.email_list.name,'_removed')

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

    def mark(self,bit):
        '''
        Mark this message using the bit provided, using field spam_score
        '''
        self.spam_score = self.spam_score | bit
        self.save()

class Attachment(models.Model):
    error = models.CharField(max_length=255,blank=True) # message if problem with attachment
    description = models.CharField(max_length=255)      # description of file contents
    filename = models.CharField(max_length=255)         # randomized archive filename
    message = models.ForeignKey(Message)
    name = models.CharField(max_length=255)             # regular name of attachment

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        path = os.path.join(reverse('archive'),'attach',self.message.email_list.name,self.filename)
        return path

    def get_file_path(self):
        directory = os.path.dirname(self.message.get_file_path())
        path = os.path.join(directory,'attachments',self.filename)
        return path

class Legacy(models.Model):
    email_list_id = models.CharField(max_length=40)
    msgid = models.CharField(max_length=255,db_index=True)
    number = models.IntegerField()

    def __unicode__(self):
        return '%s:%s' % (self.email_list_id,self.msgid)

# --------------------------------------------------
# Signal Handlers
# --------------------------------------------------

@receiver(pre_delete, sender=Message)
def _message_remove(sender, instance, **kwargs):
    '''When messages are removed, via the admin page, we need to move the message
    archive file to the "_removed" directory
    '''
    path = instance.get_file_path()
    if not os.path.exists(path):
        return
    target = instance.get_removed_dir()
    if not os.path.exists(target):
        os.mkdir(target)
    shutil.move(path,target)

@receiver([post_save, post_delete], sender=EmailList)
def _clear_cache(sender,instance, **kwargs):
    '''If EmailList object is saved or deleted remove the list_info cache entry'''
    cache.delete('list_info')