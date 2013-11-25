from django.contrib.auth.models import User
from mlarchive.archive.models import *

import datetime
import factory

class EmailListFactory(factory.DjangoModelFactory):
    FACTORY_FOR = EmailList

    name = 'test'

class MessageFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Message

    date = datetime.datetime.now()
    subject = 'This is a test message'
    frm = 'rcross@amsl.com'
    msgid = '1234567890@amsl.com'
    hashcode = 'abcd'

class ThreadFactory(factory.DjangoModelFactory):
    FACTORY_FOR = Thread

class UserFactory(factory.DjangoModelFactory):
    FACTORY_FOR = User

    username = 'admin'
    password = 'pass'

