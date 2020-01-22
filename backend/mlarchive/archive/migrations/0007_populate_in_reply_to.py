# -*- coding: utf-8 -*-


import re

from django.db import migrations


MESSAGE_ID_RE = re.compile(r'<(.*?)>')


def batch_qs(qs, batch_size=1000):
    """
    Returns a (start, end, total, queryset) tuple for each batch in the given
    queryset.

    Usage:
        # Make sure to order your querset
        article_qs = Article.objects.order_by('id')
        for start, end, total, qs in batch_qs(article_qs):
            print "Now processing %s - %s of %s" % (start + 1, end, total)
            for article in qs:
                print article.body
    """
    total = qs.count()
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        yield (start, end, total, qs[start:end])


def get_replies(apps, schema_editor):
    '''Traverse all message records, read in_reply_to_value and
    populate in_reply_to FK'''
    Message = apps.get_model("archive", "Message")

    message_qs = Message.objects.order_by('id')
    for start, end, total, qs in batch_qs(message_qs):
        for message in qs:
            msgids = MESSAGE_ID_RE.findall(message.in_reply_to_value)
            if not msgids:
                continue

            msgid = msgids[0]
            try:
                reply_message = Message.objects.get(msgid=msgid, email_list=message.email_list)
            except Message.DoesNotExist:
                reply_message = Message.objects.filter(msgid=msgid).first()

            if reply_message:
                try:
                    message.in_reply_to = reply_message
                    message.save()
                except ValueError:
                    import sys
                    print(("message:{}:{}".format(message.pk, type(message))))
                    print(("reply_message:{}:{}".format(reply_message.pk, type(reply_message))))
                    sys.exit()


def reverse_get_replies(apps, schema_editor):
    Message = apps.get_model("archive", "Message")
    Message.objects.all().update(in_reply_to=None)


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0006_message_in_reply_to'),
    ]

    operations = [
        migrations.RunPython(get_replies, reverse_get_replies),
    ]
