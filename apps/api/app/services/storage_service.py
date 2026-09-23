"""Object storage via MinIO's S3-compatible API (§63).

The database stores keys, never bytes. Keys are UUID-based and never derived
from the uploaded filename, so a hostile filename cannot traverse paths or
collide with another tenant's object (§61).
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config.settings import get_settings

#: Magic-number prefixes. The declared Content-Type is attacker-controlled, so
#: the real type is sniffed from the bytes (§61).
MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
]

SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


class StorageError(Exception):
    pass


class UnsupportedFileType(Exception):
    """The bytes are not one of the accepted types, whatever was declared."""


class UploadTooLarge(UnsupportedFileType):
    """The upload exceeded the configured byte limit."""


@dataclass
class StoredObject:
    key: str
    bucket: str
    size_bytes: int
    checksum_sha256: str
    detected_mime: str


async def read_upload(upload) -> bytes:
    """Read at most one byte beyond the upload limit.

    Reading an untrusted multipart body without a bound lets one request fill
    process memory before ``put_document`` gets a chance to reject it.
    """
    limit = get_settings().max_upload_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise UploadTooLarge(f"file is larger than the {limit}-byte limit")
    return data


@lru_cache
def _client():
    settings = get_settings()
    scheme = "https" if settings.minio_secure else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def sniff_mime(data: bytes) -> str | None:
    """Detect the real type from magic bytes. Returns None if unrecognised."""
    for signature, mime in MAGIC_SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


def sanitize_filename(name: str | None) -> str | None:
    """Strip anything that could be interpreted as a path.

    Only ever used for display; it never forms part of the storage key.
    """
    if not name:
        return None
    base = name.replace("\\", "/").split("/")[-1]
    cleaned = SAFE_FILENAME.sub("_", base)[:255]
    return cleaned or None


def build_key(prefix: str, mime: str) -> str:
    """UUID-based object key. Never derived from user input."""
    extension = mimetypes.guess_extension(mime) or ".bin"
    if extension == ".jpe":
        extension = ".jpg"
    return f"{prefix}/{uuid.uuid4().hex}{extension}"


def put_document(
    data: bytes,
    *,
    declared_mime: str | None = None,
    prefix: str = "documents",
    bucket: str | None = None,
) -> StoredObject:
    """Validate and store an uploaded file.

    Validation order matters: the type is decided by SNIFFING the bytes, and
    the declared Content-Type is only cross-checked afterwards. An `.exe`
    renamed to `.pdf` therefore fails on content, not on extension.
    """
    settings = get_settings()

    if not data:
        raise UnsupportedFileType("empty file")
    if len(data) > settings.max_upload_bytes:
        raise UploadTooLarge(
            f"file is {len(data)} bytes, limit is {settings.max_upload_bytes}"
        )

    detected = sniff_mime(data)
    if detected is None:
        raise UnsupportedFileType(
            "file content is not a supported document type "
            f"(accepted: {', '.join(sorted(settings.allowed_mime_set))})"
        )
    if detected not in settings.allowed_mime_set:
        raise UnsupportedFileType(f"{detected} is not an accepted document type")
    # A mismatched declared_mime is not fatal: the sniffed type always wins.

    target_bucket = bucket or settings.minio_bucket_documents
    key = build_key(prefix, detected)
    checksum = hashlib.sha256(data).hexdigest()

    try:
        _client().put_object(
            Bucket=target_bucket, Key=key, Body=data, ContentType=detected
        )
    except ClientError as exc:
        raise StorageError(f"could not store object: {exc}") from exc

    return StoredObject(
        key=key,
        bucket=target_bucket,
        size_bytes=len(data),
        checksum_sha256=checksum,
        detected_mime=detected,
    )


def put_bytes(data: bytes, key: str, mime: str, bucket: str | None = None) -> str:
    """Store a derived artefact (page render, enhanced image) without sniffing."""
    settings = get_settings()
    target = bucket or settings.minio_bucket_derived
    try:
        _client().put_object(Bucket=target, Key=key, Body=data, ContentType=mime)
    except ClientError as exc:
        raise StorageError(f"could not store object: {exc}") from exc
    return key


def get_bytes(key: str, bucket: str | None = None) -> bytes:
    settings = get_settings()
    target = bucket or settings.minio_bucket_documents
    try:
        response = _client().get_object(Bucket=target, Key=key)
        return response["Body"].read()
    except ClientError as exc:
        raise StorageError(f"could not read {key}: {exc}") from exc


def presigned_url(key: str, bucket: str | None = None, expires: int = 900) -> str:
    """Short-lived read URL (§61 secure object URLs)."""
    settings = get_settings()
    target = bucket or settings.minio_bucket_documents
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": target, "Key": key}, ExpiresIn=expires
    )


def derived_bucket() -> str:
    return get_settings().minio_bucket_derived


def put_page_image(image) -> str:
    """Store a rendered page as PNG in the derived bucket; return its key."""
    from ingest.rasterize import encode_png

    key = build_key("pages", "image/png")
    put_bytes(encode_png(image), key, "image/png")
    return key
