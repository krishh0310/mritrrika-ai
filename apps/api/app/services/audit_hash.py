"""Canonicalisation and hashing for the audit chain (§41).

Separated from the service so the hash function can be tested and re-run
independently of the database -- chain verification must not depend on the
same code path that wrote the rows.

This is a hash-chained append-only log. It is NOT a blockchain and must never
be described as one (§69): there is no distributed consensus and no proof of
work. What it does give is tamper-evidence -- altering or removing any event
invalidates every hash after it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def canonicalize(payload: dict[str, Any]) -> str:
    """Deterministic JSON for hashing.

    Sorted keys, no insignificant whitespace, non-ASCII preserved rather than
    escaped. Any variation here silently breaks verification later, so the
    format is fixed and tested.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_event_hash(
    *,
    sequence: int,
    timestamp: str,
    actor_id: str | None,
    actor_role: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    before_state: dict | None,
    after_state: dict | None,
    reason: str | None,
    previous_hash: str,
) -> str:
    """SHA-256 over the canonical form of the event AND its predecessor's hash.

    Including previous_hash is what chains the log: re-computing any event
    requires every earlier event to be unchanged.
    """
    body = canonicalize(
        {
            "sequence": sequence,
            "timestamp": timestamp,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before_state": before_state,
            "after_state": after_state,
            "reason": reason,
            "previous_hash": previous_hash,
        }
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
