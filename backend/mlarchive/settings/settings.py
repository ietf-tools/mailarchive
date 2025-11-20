# settings/settings.py
from .base import *

import botocore.config

# Console logs as JSON instead of plain when running in k8s
LOGGING["handlers"]["console"]["formatter"] = "json"

for storagename in ARTIFACT_STORAGE_NAMES:
    if storagename in ["staging"]:
        continue
    replica_storagename = f"r2-{storagename}"
    STORAGES[replica_storagename] = {
        "BACKEND": "mlarchive.archive.storage.MetadataS3Storage",
        "OPTIONS": dict(
            endpoint_url=env('BLOB_STORE_ENDPOINT_URL'),
            access_key=env('BLOB_STORE_ACCESS_KEY'),
            secret_key=env('BLOB_STORE_SECRET_KEY'),
            security_token=None,
            client_config=botocore.config.Config(
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                signature_version="s3v4",
                connect_timeout=env('BLOB_STORE_CONNECT_TIMEOUT'),
                read_timeout=env('BLOB_STORE_READ_TIMEOUT'),
                retries={"total_max_attempts": env('BLOB_STORE_MAX_ATTEMPTS')},
            ),
            verify=False,
            bucket_name=f"{env('BLOB_STORE_BUCKET_PREFIX')}{storagename}".strip(),
            ietf_log_blob_timing=env('BLOB_STORE_ENABLE_PROFILING'),
        ),
    }
