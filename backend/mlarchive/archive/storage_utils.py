# Copyright The IETF Trust 2025, All Rights Reserved
import datetime
import secrets
from io import BufferedReader
from typing import Iterator, NamedTuple, Optional, Union

# import debug  # pyflakes ignore

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import storages, Storage
from mlarchive.archive.models import StoredObject
from mlarchive.blobdb.storage import BlobFile
from mlarchive.blobdb.replication import destination_storage_for

import logging
logger = logging.getLogger(__name__)


def _get_storage(kind: str) -> Storage:
    if kind in settings.ARTIFACT_STORAGE_NAMES:
        return storages[kind]
    else:
        # debug.say(f"Got into not-implemented looking for {kind}")
        raise NotImplementedError(f"Don't know how to store {kind}")


def exists_in_storage(kind: str, name: str) -> bool:
    if settings.ENABLE_BLOBSTORAGE:
        try:
            # Storage.exists() is a metadata-only lookup. Do not use open(),
            # which reads the entire blob just to answer a yes/no.
            return _get_storage(kind).exists(name)
        except FileNotFoundError:
            return False
        except Exception as err:
            logger.error(f"Blobstore Error: Failed to test existence of {kind}:{name}: {repr(err)}")
            raise
    return False


def remove_from_storage(kind: str, name: str, warn_if_missing: bool = True) -> None:
    if settings.ENABLE_BLOBSTORAGE:
        try:
            if exists_in_storage(kind, name):
                _get_storage(kind).delete(name)
            elif warn_if_missing:
                complaint = (
                    f"WARNING: Asked to delete non-existent {name} from {kind} storage"
                )
                logger.info(complaint)
        except Exception as err:
            logger.warning(f"Blobstore Error: Failed to remove {kind}:{name}: {repr(err)}")
            raise
    return None


def store_file(
    kind: str,
    name: str,
    file: Union[File, BufferedReader],
    allow_overwrite: bool = False,
    content_type: str = "",
    mtime: Optional[datetime.datetime] = None,
) -> None:
    if settings.ENABLE_BLOBSTORAGE:
        try:
            is_new = not exists_in_storage(kind, name)
            # debug.show('f"Asked to store {name} in {kind}: is_new={is_new}, allow_overwrite={allow_overwrite}"')
            if not allow_overwrite and not is_new:
                # debug.show('f"Failed to save {kind}:{name} - name already exists in store"')
                raise RuntimeError(f"Failed to save {kind}:{name} - name already exists in store")
            new_name = _get_storage(kind).save(
                name,
                BlobFile(
                    content=file.read(),
                    name=name,
                    mtime=mtime,
                    content_type=content_type,
                ),
            )
            if new_name != name:
                complaint = f"Error encountered saving '{name}' - results stored in '{new_name}' instead."
                logger.error(f"Blobstore Error: {complaint}")
                raise RuntimeError(complaint)
        except Exception as err:
            logger.error(f"Blobstore Error: Failed to store file {kind}:{name}: {repr(err)}")
            raise
    return None


def store_bytes(
    kind: str,
    name: str,
    content: bytes,
    allow_overwrite: bool = False,
    content_type: str = "",
    mtime: Optional[datetime.datetime] = None,
) -> None:
    if settings.ENABLE_BLOBSTORAGE:
        try:
            store_file(
                kind,
                name,
                ContentFile(content),
                allow_overwrite,
                content_type,
                mtime,
            )
        except Exception as err:
            # n.b., not likely to get an exception here because store_file or store_bytes will catch it
            logger.error(f"Blobstore Error: Failed to store bytes to {kind}:{name}: {repr(err)}")
            raise
    return None


def store_str(
    kind: str,
    name: str,
    content: str,
    allow_overwrite: bool = False,
    content_type: str = "",
    mtime: Optional[datetime.datetime] = None,
) -> None:
    if settings.ENABLE_BLOBSTORAGE:
        try:
            content_bytes = content.encode("utf-8")
            store_bytes(
                kind,
                name,
                content_bytes,
                allow_overwrite,
                content_type,
                mtime,
            )
        except Exception as err:
            # n.b., not likely to get an exception here because store_file or store_bytes will catch it
            logger.error(f"Blobstore Error: Failed to store string to {kind}:{name}: {repr(err)}")
            raise
    return None


def retrieve_bytes(kind: str, name: str) -> bytes:
    from mlarchive.archive.storage import maybe_log_timing
    content = b""
    if settings.ENABLE_BLOBSTORAGE:
        try:
            store = _get_storage(kind)
            with store.open(name) as f:
                with maybe_log_timing(
                    hasattr(store, "ietf_log_blob_timing") and store.ietf_log_blob_timing,
                    "read",
                    bucket_name=store.bucket_name if hasattr(store, "bucket_name") else "",
                    name=name,
                ):
                    content = f.read()
        except Exception as err:
            logger.error(f"Blobstore Error: Failed to read bytes from {kind}:{name}: {repr(err)}")
            raise
    return content


def retrieve_str(kind: str, name: str) -> str:
    content = ""
    if settings.ENABLE_BLOBSTORAGE:
        try:
            content_bytes = retrieve_bytes(kind, name)
            content = content_bytes.decode("utf-8")
        except Exception as err:
            logger.error(f"Blobstore Error: Failed to read string from {kind}:{name}: {repr(err)}")
            raise
    return content


class StoredObjectMetadata(NamedTuple):
    """What the index records about one live object."""

    store: str
    name: str
    sha384: str
    len: int
    store_created: datetime.datetime
    modified: datetime.datetime


def _store_for(kind: str) -> str:
    """Return the StoredObject.store value for the storage alias kind."""
    return getattr(_get_storage(kind), "bucket_name", kind)


def list_names(
    kind: str,
    prefix: Optional[str] = None,
    modified_before: Optional[datetime.datetime] = None,
) -> Iterator[str]:
    """Iterate, in name order, over the names of the live objects held in kind.

    The Storage API has no listing operation, so this is answered from the
    StoredObject index rather than from the storage itself. It is only as complete as
    the index, which the reconcile task keeps in step with the bytes. With prefix,
    only names starting with it are returned; with modified_before, only objects last
    modified before that instant.
    """
    if not settings.ENABLE_BLOBSTORAGE:
        return iter(())
    queryset = StoredObject.objects.filter(store=_store_for(kind)).exclude_deleted()
    if prefix is not None:
        if not prefix:
            raise ValueError("prefix must be non-empty")
        queryset = queryset.filter(name__startswith=prefix)
    if modified_before is not None:
        queryset = queryset.filter(modified__lt=modified_before)
    return queryset.order_by("name").values_list("name", flat=True).iterator(chunk_size=5000)


def get_metadata(kind: str, name: str) -> Optional[StoredObjectMetadata]:
    """Return what the index records about the live object name in kind, or None.

    None means the index has no live row: the object was never indexed, or has been
    deleted. It does not by itself prove the bytes are absent; exists_in_storage
    asks the storage that question.
    """
    if not settings.ENABLE_BLOBSTORAGE:
        return None
    row = (
        StoredObject.objects
        .filter(store=_store_for(kind), name=name)
        .exclude_deleted()
        .values_list("store", "name", "sha384", "len", "store_created", "modified")
        .first()
    )
    return None if row is None else StoredObjectMetadata(*row)


def find_by_checksum(sha384: str, exclude_kinds: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """Return the (store, name) of every live object whose content has this digest.

    This is the cross-store question the Storage API cannot ask at all: the same bytes
    stored under any name in any store. Stores named in exclude_kinds are left out.
    Trusting the digest as proof of identical content is deliberate; it is why the
    digest is indexed.
    """
    if not settings.ENABLE_BLOBSTORAGE:
        return []
    queryset = StoredObject.objects.filter(sha384=sha384).exclude_deleted()
    if exclude_kinds:
        queryset = queryset.exclude(store__in=[_store_for(kind) for kind in exclude_kinds])
    return list(queryset.order_by("store", "name").values_list("store", "name"))


def get_unique_blob_name(prefix, bucket):
    storage = storages[bucket]
    for _ in range(1000):
        token = secrets.token_hex(8)
        blob_name = f'{prefix}{token}'
        if not storage.exists(blob_name):
            return blob_name
    msg = 'Blobstore Error: get_unique_blob_name() failed.'
    logger.error(msg)
    raise RuntimeError(msg)


def move_object(key: str, source_bucket: str, target_bucket: str) -> None:
    if settings.ENABLE_BLOBSTORAGE:
        try:
            store = _get_storage(target_bucket)
            content = retrieve_bytes(source_bucket, key)
            store_bytes(target_bucket, key, content=content)
            assert exists_in_storage(target_bucket, key)
            assert store.size(key) == len(content)
            remove_from_storage(source_bucket, key)
        except Exception as err:
            logger.error(f"Blobstore Error: Failed to move {key} from {source_bucket} to {target_bucket} {repr(err)}")
            raise
    return
