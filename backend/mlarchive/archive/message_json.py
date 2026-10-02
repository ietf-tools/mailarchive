# Copyright The IETF Trust 2026, All Rights Reserved

"""Write the ml-messages-json blobs used by the Cloudflare worker.

Which blobs to write, and when, is decided by archive.derived. The JSON
includes the rendered message body, which links to the message's Attachment
records, so it can only be written once the message is fully archived, not
from a Message post_save signal. See MessageWrapper.save().
"""

import io
import logging

from mlarchive.archive.storage_utils import store_file

logger = logging.getLogger(__name__)


def store_message_json(message, nav=None):
    """Write the ml-messages-json blob for one message.

    nav is an optional dict of the message's navigation URLs, as produced by
    fetch_nav_for_batch; without it as_json() looks each neighbour up itself.
    """
    store_file(
        kind='ml-messages-json',
        name=message.get_blob_name(),
        file=io.BytesIO(message.as_json(nav=nav).encode('utf-8')),
        allow_overwrite=True,
        content_type='application/json'
    )
