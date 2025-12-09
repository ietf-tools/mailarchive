# Copyright The IETF Trust 2025, All Rights Reserved

import debug  # pyflakes:ignore
import json

from contextlib import contextmanager
from storages.backends.s3 import S3Storage

from django.core.files.base import File

from django.utils import timezone

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
