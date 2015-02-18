from email.utils import parseaddr
import os
import re
import shutil
import subprocess

from django.db.models.signals import pre_delete, post_delete, post_save
from django.dispatch.dispatcher import receiver
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db import models
from django.template.loader import render_to_string

from mlarchive.archive.generator import Generator

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
    first = models.ForeignKey('Message',related_name='thread_key',blank=True,null=True)  # first message in thread, by date
    date = models.DateTimeField(db_index=True)     # date of first message

    def __unicode__(self):
        return str(self.id)

    def set_first(self, message=None):
        """Sets the first message of the thread.  Call when adding or removing
        messages
        """
        if not message:
            message = self.message_set.all().order_by('date').first()
        self.first = message
        self.date = message.date
        self.save()

class EmailList(models.Model):
    active = models.BooleanField(default=True,db_index=True)
    alias = models.CharField(max_length=255,blank=True)
    created = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255,blank=True)
    members = models.ManyToManyField(User)
    members_digest = models.CharField(max_length=28,blank=True)
    name = models.CharField(max_length=255,db_index=True,unique=True)
    private = models.BooleanField(default=False,db_index=True)
    updated = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.name

    @staticmethod
    def get_attachments_dir(listname):
        return os.path.join(settings.ARCHIVE_DIR,listname,'_attachments')

    @property
    def attachments_dir(self):
        return self.get_attachments_dir(self.name)

    @staticmethod
    def get_failed_dir(listname):
        return os.path.join(settings.ARCHIVE_DIR,listname,'_failed')

    @property
    def failed_dir(self):
        return self.get_failed_dir(self.name)

    @staticmethod
    def get_removed_dir(listname):
        return os.path.join(settings.ARCHIVE_DIR,listname,'_removed')

    @property
    def removed_dir(self):
        return self.get_removed_dir(self.name)

class Message(models.Model):
    base_subject = models.CharField(max_length=512,blank=True)
    cc = models.TextField(blank=True,default='')
    date = models.DateTimeField(db_index=True)
    email_list = models.ForeignKey(EmailList,db_index=True)
    frm = models.CharField(max_length=255,blank=True)          # really long from lines are spam
    from_line = models.CharField(max_length=255,blank=True)
    hashcode = models.CharField(max_length=28,db_index=True)
    in_reply_to = models.TextField(blank=True,default='')     # in-reply-to header field
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
        """Returns the message formated as HTML.  Uses MHonarc standalone
        Not used as of v1.00
        """
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

    @property
    def friendly_frm(self):
        pass

    @property
    def frm_email(self):
        """This property is the email portion of the "From" header all lowercase
        (the realname is stripped).  It is used in faceting search results as well
        as display.
        """
        return parseaddr(self.frm)[1].lower()

    def get_absolute_url(self):
        # strip padding, "=", to shorten URL
        return reverse('archive_detail',kwargs={'list_name':self.email_list.name,
                                                'id':self.hashcode.rstrip('=')})

    def get_attachment_path(self):
        path = self.email_list.attachments_dir
        if not os.path.exists(path):
            os.makedirs(path)
            os.chmod(path,02777)
        return path

    def get_body(self):
        """Returns the contents of the message body, text only for use in indexing.
        ie. HTML is stripped.  This is called from the index template.
        """
        gen = Generator(self)
        return gen.as_text()

    def get_body_html(self, request=None):
        """Returns the contents of the message body with as HTML, for use in display
        """
        gen = Generator(self)
        return gen.as_html(request=request)

    def get_body_raw(self):
        """Returns the raw contents of the message file.
        NOTE: this will include encoded attachments
        """
        try:
            with open(self.get_file_path()) as f:
                return f.read()
        except IOError as error:
            msg = 'Error reading message file: %s' % self.get_file_path()
            logger.warning(msg)
            return msg

    def get_file_path(self):
        return os.path.join(settings.ARCHIVE_DIR,self.email_list.name,self.hashcode)

    def get_from_line(self):
        """Returns the "From " envelope header from the original mbox file if it
        exists or constructs one.  Useful when exporting in mbox format.
        """
        if self.from_line:
            return 'From {0}'.format(self.from_line)
        else:
            try:
                output = 'From {0} {1}'.format(self.frm_email,self.date.strftime('%a %b %d %H:%M:%S %Y'))
            except UnicodeEncodeError:
                output = 'From {0} {1}'.format(self.frm_email.encode("ascii","ignore"),self.date.strftime('%a %b %d %H:%M:%S %Y'))
            return output

    def get_removed_dir(self):
        return self.email_list.removed_dir

    def list_by_date_url(self):
        return reverse('archive_search') + '?email_list={}&index={}'.format(self.email_list.name,self.hashcode.rstrip('='))
        
    def list_by_thread_url(self):
        return reverse('archive_search') + '?email_list={}&gbt=1&index={}'.format(self.email_list.name,self.hashcode.rstrip('='))
    
    def mark(self,bit):
        """Mark this message using the bit provided, using field spam_score
        """
        self.spam_score = self.spam_score | bit
        self.save()

    @property
    def thread_date(self):
        """Returns the date of the first message in the associated thread.  Use for
        grouping by Thread
        """
        return self.thread.date

    @property
    def to_and_cc(self):
        """Returns 'To' and 'CC' fields combined, for use in indexing
        """
        if self.cc:
            return self.to + ' ' + self.cc
        else:
            return self.to

class Attachment(models.Model):
    error = models.CharField(max_length=255,blank=True) # message if problem with attachment
    description = models.CharField(max_length=255)      # description of file contents
    filename = models.CharField(max_length=255)         # randomized archive filename
    message = models.ForeignKey(Message)
    name = models.CharField(max_length=255)             # regular name of attachment

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return os.path.join(reverse('archive'),'attach',self.message.email_list.name,self.filename)

    def get_file_path(self):
        return os.path.join(self.message.get_atttachment_path(),self.filename)

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
    """When messages are removed, via the admin page, we need to move the message
    archive file to the "_removed" directory
    """
    path = instance.get_file_path()
    if not os.path.exists(path):
        return
    target = instance.get_removed_dir()
    if not os.path.exists(target):
        os.mkdir(target)
        os.chmod(target,02777)
    shutil.move(path,target)

    # TODO
    # if this message was the first in the thread reset
    #if instance == instance.thread.first:
    #   instance.thread.set_first(ignore=instance)

@receiver(post_save, sender=Message)
def _message_save(sender, instance, **kwargs):
    """When messages are saved, call thread.set_first()
    """
    if instance.date < instance.thread.date:
        instance.thread.set_first(instance)

@receiver([post_save, post_delete], sender=EmailList)
def _clear_cache(sender,instance, **kwargs):
    """If EmailList object is saved or deleted remove the list_info cache entry"""
    cache.delete('list_info')

