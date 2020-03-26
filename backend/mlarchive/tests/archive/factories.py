from django.contrib.auth.models import User
from mlarchive.archive.models import Message, EmailList, Thread, Attachment

import datetime
import factory
import string
import random

from mlarchive.archive.mail import get_base_subject


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
    base_subject = get_base_subject(subject)
    frm = 'John Smith <john@example.com>'
    msgid = factory.Sequence(lambda n: "%03d@example.com" % n)
    hashcode = factory.Sequence(lambda n: "abcdefghijklmnopqrstuvx%04d=" % n)
    thread = factory.SubFactory(ThreadFactory)
    # email_list = factory.SubFactory(EmailListFactory)


class AttachmentFactory(factory.DjangoModelFactory):
    class Meta:
        model = Attachment

    name = 'attachment.txt'
    content_type = 'text/plain'
    content_disposition = 'attachment'
    sequence = factory.Sequence(lambda n: n + 1)


class UserFactory(factory.DjangoModelFactory):
    class Meta:
        model = User

    email = 'admin@admin.com'
    username = 'admin'
    password = factory.PostGenerationMethodCall('set_password', 'admin')
