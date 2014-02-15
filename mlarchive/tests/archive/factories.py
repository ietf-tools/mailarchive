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

class MessageFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Message

    date = datetime.datetime.now()
    subject = 'This is a test message'
    frm = 'rcross@amsl.com'
    msgid = id_generator() + '@amsl.com'
    hashcode = id_generator()
    thread = ThreadFactory.create()

class UserFactory(factory.DjangoModelFactory):
    FACTORY_FOR = User

    username = 'admin'
    password = 'pass'

