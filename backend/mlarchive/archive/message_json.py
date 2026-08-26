# Copyright The IETF Trust 2026, All Rights Reserved

"""Write the ml-messages-json blobs used by the Cloudflare worker.

These are written once the message is fully archived, not from a Message
post_save signal, because the serialized JSON includes the rendered message
body, which links to the message's Attachment records.  Those records can only
be created after the Message has a primary key, ie. after post_save has run.
See MessageWrapper.save().
"""

import io
import logging

from mlarchive.archive.storage_utils import store_file

logger = logging.getLogger(__name__)


def store_message_json(message):
    """Write the ml-messages-json blob for one message."""
    store_file(
        kind='ml-messages-json',
        name=message.get_blob_name(),
        file=io.BytesIO(message.as_json().encode('utf-8')),
        allow_overwrite=True,
        content_type='application/json'
    )


def write_message_json(message):
    """Write the JSON blobs affected by a newly archived message.

    Writes the blob for the message itself, then refreshes the blobs of the
    neighboring messages whose navigation links the new message invalidates.
    Private messages have no JSON blob.
    """
    if message.email_list.private:
        return
    store_message_json(message)
    if message.thread_order > 0:
        update_message_json_thread(message)
    update_message_json_list(message)


def update_message_json_thread(message):
    """Write ml-messages-json for all other messages in thread.

    TODO: consider alternatives like client retrieving thread instead of
    computing
    """
    for msg in message.thread.message_set.exclude(pk=message.pk):
        store_message_json(msg)


def update_message_json_list(message):
    """Write ml-messages-json for the previous message in list order.

    Its next_in_list link becomes stale when a new message is added after it.
    """
    prev_msg = message.previous_in_list()
    if prev_msg:
        store_message_json(prev_msg)
