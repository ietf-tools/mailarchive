from django.contrib.auth.models import User
from mlarchive.archive.models import *

import datetime
import factory
import string
import random

def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

class EmailListFactory(factory.DjangoModelFactory):
    FACTORY_FOR = EmailList

    name = 'test'

class ThreadFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Thread
    
    date = datetime.datetime.now()
    
class MessageFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Message

    date = datetime.datetime.now().replace(second=0,microsecond=0)
    subject = 'This is a test message'
    frm = 'rcross@amsl.com'
    #msgid = id_generator() + '@amsl.com'
    #hashcode = id_generator()
    #thread = ThreadFactory.create()
    msgid = factory.Sequence(lambda n: "%03d@amsl.com" % n)
    hashcode = factory.Sequence(lambda n: "a%03d" % n)
    thread = factory.SubFactory(ThreadFactory)

class UserFactory(factory.DjangoModelFactory):
    FACTORY_FOR = User

    email = 'admin@admin.com'
    username = 'admin'
    password = factory.PostGenerationMethodCall('set_password', 'admin')

