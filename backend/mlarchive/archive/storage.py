# Copyright The IETF Trust 2025, All Rights Reserved

import debug  # pyflakes:ignore
import json

from contextlib import contextmanager
from storages.backends.s3 import S3Storage

from django.core.files.base import File

from django.utils import timezone

from mlarchive.archive.models import StoredObject
from mlarchive.blobdb.storage import BlobdbStorage, MetadataFile

import logging
logger = logging.getLogger(__name__)


@contextmanager
def maybe_log_timing(enabled, op, **kwargs):
    """If enabled, log elapsed time and additional data from kwargs

    Emits log even if an exception occurs
    """
    before = timezone.now()
    exception = None
    try:
        yield
    except Exception as err:
        exception = err
        raise
    finally:
        if enabled:
            dt = timezone.now() - before
            logger.info(
                json.dumps(
                    {
                        "log": "S3Storage_timing",
                        "seconds": dt.total_seconds(),
                        "op": op,
                        "exception": "" if exception is None else repr(exception),
                        **kwargs,
                    }
                )
            )


class MetadataS3Storage(S3Storage):
    def get_default_settings(self):
        # add a default for the ietf_log_blob_timing boolean
        return super().get_default_settings() | {"ietf_log_blob_timing": False}

    def _save(self, name, content: File):
        with maybe_log_timing(
            self.ietf_log_blob_timing, "_save", bucket_name=self.bucket_name, name=name
        ):
            return super()._save(name, content)

    def _open(self, name, mode="rb"):
        with maybe_log_timing(
            self.ietf_log_blob_timing,
            "_open",
            bucket_name=self.bucket_name,
            name=name,
            mode=mode,
        ):
            return super()._open(name, mode)

    def delete(self, name):
        with maybe_log_timing(
            self.ietf_log_blob_timing, "delete", bucket_name=self.bucket_name, name=name
        ):
            super().delete(name)

    def _get_write_parameters(self, name, content=None):
        debug.show('f"getting write parameters for {name}"')
        params = super()._get_write_parameters(name, content)
        # If we have a non-empty explicit content type, use it
        content_type = getattr(content, "content_type", "").strip()
        if content_type != "":
            params["ContentType"] = content_type
        if "Metadata" not in params:
            params["Metadata"] = {}
        if hasattr(content, "custom_metadata"):
            params["Metadata"].update(content.custom_metadata)
        return params


class StoredObjectBlobdbStorage(BlobdbStorage):
    """BlobdbStorage that also records object metadata in the StoredObject table.

    The bytes are authoritative; the StoredObject row is an index over them. The two
    live in different databases, so neither write can be made atomic with the other.
    The ordering of every operation here upholds one invariant: a live StoredObject
    row never outlives the bytes it describes. Callers such as purge_incoming treat a
    matching row as proof that content is safely archived, so a row pointing at bytes
    that are gone would let them delete the last remaining copy.

    That invariant makes the two operations asymmetric:

    - Saving writes the bytes first. If recording the metadata then fails, the result
      is a missing index entry, which the reconcile task repairs, so the failure is
      logged and the save still succeeds.
    - Deleting tombstones the metadata first. If that fails the bytes are left alone
      and the exception propagates, because continuing would leave a live row
      describing content that no longer exists.
    """

    def _metadata_for(self, name, content):
        """Return the custom metadata dict for content, or None if it cannot be read.

        Anything written through storage_utils is a MetadataFile and already knows how
        to produce its own digest. A plain Django File does not, so wrap it in one
        rather than duplicating the computation here. Unseekable content cannot be
        digested at all, and under the log-and-continue policy that must not stop the
        bytes from being stored, so failure is reported as None.
        """
        try:
            metadata = getattr(content, 'custom_metadata', None)
            if metadata is None:
                metadata = MetadataFile(file=content).custom_metadata
            return metadata
        except Exception as err:
            logger.error(
                f'Blobstore Error: could not read metadata for {self.bucket_name}:{name}: '
                f'{repr(err)}'
            )
            return None

    def _save_stored_object(self, name, content, metadata):
        """Create or refresh the StoredObject row describing name."""
        sha384 = metadata['sha384']
        length = int(metadata['len'])
        content_type = getattr(content, 'content_type', '')
        mtime = getattr(content, 'mtime', None)
        now = timezone.now()

        record, created = StoredObject.objects.get_or_create(
            store=self.bucket_name,
            name=name,
            defaults=dict(
                sha384=sha384,
                len=length,
                content_type=content_type,
                mtime=mtime,
                store_created=now,
                created=now,
                modified=now,
            ),
        )
        if created:
            return record

        # An existing row is refreshed only when something about the object actually
        # changed, so that re-storing identical content leaves modified alone. A
        # tombstoned row always counts as changed: the object is back.
        unchanged = (
            record.sha384 == sha384
            and record.len == length
            and record.content_type == content_type
            and record.mtime == mtime
            and record.deleted is None
        )
        if unchanged:
            return record

        record.sha384 = sha384
        record.len = length
        record.content_type = content_type
        record.mtime = mtime
        record.modified = now
        record.deleted = None
        record.save()
        return record

    def _delete_stored_object(self, name):
        """Tombstone the StoredObject row for name, returning the number updated.

        Zero is not an error. Until the backfill has run most objects predate this
        table, and detecting that drift is the reconcile task's job, not this one's.
        """
        return (
            StoredObject.objects
            .filter(store=self.bucket_name, name=name)
            .exclude_deleted()
            .update(deleted=timezone.now())
        )

    def _save(self, name, content):
        # Digest the content before the save consumes it, while the file position is
        # still known good. MetadataFile caches its result, so a caller that already
        # computed the metadata does not pay for it twice.
        metadata = self._metadata_for(name, content)
        saved_name = super()._save(name, content)
        if metadata is None:
            return saved_name
        try:
            self._save_stored_object(saved_name, content, metadata)
        except Exception as err:
            logger.error(
                f'Blobstore Error: stored {self.bucket_name}:{saved_name} but failed to '
                f'record its StoredObject: {repr(err)}'
            )
        return saved_name

    def delete(self, name):
        self._delete_stored_object(name)
        super().delete(name)
