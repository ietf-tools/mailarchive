from django.contrib.auth.models import User
from mlarchive.archive.models import *

import datetime
import factory
import string
import random


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


class EmailListFactory(factory.DjangoModelFactory):
    class Meta:
        model = EmailList

    name = 'public'


class ThreadFactory(factory.DjangoModelFactory):
    class Meta:
        model = Thread

    date = datetime.datetime.now().replace(second=0, microsecond=0)


class MessageFactory(factory.DjangoModelFactory):
    class Meta:
        model = Message

    date = datetime.datetime.now().replace(second=0, microsecond=0)
    subject = 'This is a test message'
    frm = 'john@example.com'
    msgid = factory.Sequence(lambda n: "%03d@example.com" % n)
    hashcode = factory.Sequence(lambda n: "a%03d=" % n)
    thread = factory.SubFactory(ThreadFactory)
    # email_list = factory.SubFactory(EmailListFactory)

class UserFactory(factory.DjangoModelFactory):
    class Meta:
        model = User

    email = 'admin@admin.com'
    username = 'admin'
    password = factory.PostGenerationMethodCall('set_password', 'admin')
