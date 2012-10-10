from django.db import models
from django.conf import settings
from django.core.urlresolvers import reverse
#from ietf.group.models import Group
#from ietf.name.models import RoleName
#from ietf.person.models import Person

import os

class Thread(models.Model):
    pass
    
class EmailList(models.Model):
    active = models.BooleanField(default=True,db_index=True)
    date_created = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255,blank=True)
    name = models.CharField(max_length=255,db_index=True)
    private = models.BooleanField(default=False,db_index=True)
    alias = models.CharField(max_length=255,blank=True)

    def __unicode__(self):
        return self.name
    
class Message(models.Model):
    email_list = models.ForeignKey(EmailList,db_index=True)
    legacy_number = models.IntegerField(blank=True,null=True,db_index=True)  # for mapping mhonarc
    hashcode = models.CharField(max_length=28,db_index=True)
    msgid = models.CharField(max_length=255,db_index=True)
    date = models.DateTimeField(db_index=True)
    frm = models.CharField(max_length=255,db_index=True)
    to = models.CharField(max_length=255,blank=True)
    cc = models.CharField(max_length=255,blank=True)
    subject = models.CharField(max_length=255)
    
    headers = models.TextField()
    @property
    def body(self):
        with open(self.get_file_path()) as f:
            return f.read()
        
    inrt = models.CharField(max_length=255,blank=True)      # in-reply-to header field
    references = models.ManyToManyField('self',through='Reference',symmetrical=False)
    thread = models.ForeignKey(Thread)
    
    def __unicode__(self):
        return self.msgid

    def get_absolute_url(self):
        pass
    
    def get_file_path(self):
        return os.path.join(settings.ARCHIVE_DIR,self.email_list.name,self.hashcode)
        
    def export(self):
        '''export this message'''
        pass

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

class IetfRole(models.Model):
    email_list = models.ForeignKey(EmailList)
    group_id = models.IntegerField()
    role_slug = models.CharField(max_length=8)
    
class IetfPerson(models.Model):
    email_list = models.ForeignKey(EmailList)
    person_id = models.IntegerField()
    