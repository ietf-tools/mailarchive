from django.contrib.auth.models import User
from mlarchive.archive.models import (Message, EmailList, Thread, Attachment,
    Subscriber)

import datetime
import factory
import string
import random
from datetime import timezone

from mlarchive.archive.mail import get_base_subject
from mlarchive.archive.storage_utils import store_bytes


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


def store_message_blob(message, content):
    """Store content as the blob for message.  Use with MessageFactory, which
    creates a Message record without any content, when the test needs to read
    the message body.
    """
    store_bytes(
        message.get_blob_bucket(),
        message.get_blob_name(),
        content,
        allow_overwrite=True,
        content_type='message/rfc822')


class EmailListFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EmailList
        django_get_or_create = ('name',)

    name = 'public'


class ThreadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Thread

    date = datetime.datetime.now(timezone.utc).replace(second=0, microsecond=0)


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    date = datetime.datetime.now(timezone.utc).replace(second=0, microsecond=0)
    subject = 'This is a test message'
    base_subject = get_base_subject(subject)
    frm = 'John Smith <john@example.com>'
    msgid = factory.Sequence(lambda n: "%03d@example.com" % n)
    hashcode = factory.Sequence(lambda n: "abcdefghijklmnopqrstuvx%04d=" % n)
    thread = factory.SubFactory(ThreadFactory)
    # email_list = factory.SubFactory(EmailListFactory)


class AttachmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Attachment

    name = 'attachment.txt'
    content_type = 'text/plain'
    content_disposition = 'attachment'
    sequence = factory.Sequence(lambda n: n + 1)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = 'admin@admin.com'
    username = 'admin'
    password = factory.PostGenerationMethodCall('set_password', 'admin')

    @factory.post_generation
    def finalize_instance(self, create, extracted, **kwargs):
        """
        Custom post-generation hook to save the instance after any modifications.
        """
        if create:  # Only save if the instance was created
            self.save()


class SubscriberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subscriber

    count = 1
    date = datetime.datetime.now(timezone.utc).replace(second=0, microsecond=0)
