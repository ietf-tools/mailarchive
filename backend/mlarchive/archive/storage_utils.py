# Copyright The IETF Trust 2025, All Rights Reserved
import datetime
import secrets
from io import BufferedReader
from typing import Optional, Union

# import debug  # pyflakes ignore

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import storages, Storage
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
            store = _get_storage(kind)
            with store.open(name):
                return True
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
