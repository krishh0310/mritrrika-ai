"""Transport to a state Land Records Management System (§14).

The record format is fixed (lrms_service.ror_payload); how it reaches the
state is not, because states differ. Some LRMS instances import batches from a
drop folder that an SFTP job collects; others expose an HTTP endpoint. Each is
an adapter here, and the deployment picks one with LRMS_ADAPTER.

Every adapter obeys one contract: `deliver` either returns a receipt or raises
LrmsDeliveryError. It never reports success it did not observe -- a record
marked delivered that the state never received is worse than one visibly
pending, because nobody goes looking for it.
"""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class LrmsDeliveryError(Exception):
    """The record did not reach the LRMS. It stays queued for another attempt."""


@dataclass(frozen=True)
class Receipt:
    #: The LRMS's own reference for the record, or where it was written.
    remote_reference: str


class LrmsAdapter(ABC):
    name = "abstract"

    @abstractmethod
    def deliver(self, payload: dict, digest: str) -> Receipt:
        ...


class FileDropAdapter(LrmsAdapter):
    """Write each record as one JSON file into a drop folder.

    The file is written under a temporary name and renamed into place, so a
    collector polling the folder never picks up a half-written record. The name
    carries the digest, so redelivering the same content overwrites the same
    file instead of leaving a duplicate for the importer to reconcile.
    """

    name = "file"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def deliver(self, payload: dict, digest: str) -> Receipt:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            final = self.directory / f"{payload['record_id']}.{digest[:16]}.json"
            handle, temporary = tempfile.mkstemp(
                dir=self.directory, prefix=".partial-", suffix=".json"
            )
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(payload, out, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(temporary, final)
        except OSError as exc:
            raise LrmsDeliveryError(f"could not write to {self.directory}: {exc}") from exc
        return Receipt(remote_reference=final.name)


class HttpAdapter(LrmsAdapter):
    """POST each record to the state's endpoint.

    The digest travels as an Idempotency-Key, so a retry after a timeout -- when
    the first request may well have landed -- cannot create a second copy on a
    server that honours the header.
    """

    name = "http"

    def __init__(self, endpoint: str, token: str | None, timeout: float = 15.0) -> None:
        self.endpoint = endpoint
        self.token = token
        self.timeout = timeout

    def deliver(self, payload: dict, digest: str) -> Receipt:
        import httpx

        headers = {"Idempotency-Key": digest, "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = httpx.post(
                self.endpoint,
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise LrmsDeliveryError(f"LRMS endpoint unreachable: {exc}") from exc
        if not response.is_success:
            raise LrmsDeliveryError(
                f"LRMS endpoint answered {response.status_code}: {response.text[:300]}"
            )
        try:
            body = response.json()
        except ValueError:
            body = {}
        reference = (
            (body.get("reference") or body.get("id")) if isinstance(body, dict) else None
        )
        return Receipt(remote_reference=str(reference or digest))


class DisabledAdapter(LrmsAdapter):
    """Queue only. Records wait in the outbox until an adapter is configured."""

    name = "disabled"

    def deliver(self, payload: dict, digest: str) -> Receipt:
        raise LrmsDeliveryError("LRMS delivery is disabled (LRMS_ADAPTER=disabled)")


def build_adapter(settings) -> LrmsAdapter:
    """The adapter the deployment configured. An unknown name is an error, not
    a silent fallback to 'disabled' that would leave records quietly queued."""
    choice = (settings.lrms_adapter or "").strip().lower()
    if choice == "file":
        return FileDropAdapter(settings.lrms_outbox_dir)
    if choice == "http":
        if not settings.lrms_endpoint:
            return _Misconfigured("LRMS_ADAPTER=http but LRMS_ENDPOINT is not set")
        return HttpAdapter(
            settings.lrms_endpoint, settings.lrms_api_token, settings.lrms_timeout_seconds
        )
    if choice == "disabled":
        return DisabledAdapter()
    return _Misconfigured(f"unknown LRMS_ADAPTER {settings.lrms_adapter!r}")


class _Misconfigured(LrmsAdapter):
    """Fails every delivery with the configuration error, so it is visible on
    each queued record rather than only in a startup log."""

    name = "misconfigured"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def deliver(self, payload: dict, digest: str) -> Receipt:
        raise LrmsDeliveryError(self.reason)


__all__ = [
    "DisabledAdapter", "FileDropAdapter", "HttpAdapter", "LrmsAdapter",
    "LrmsDeliveryError", "Receipt", "build_adapter",
]
