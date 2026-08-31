#!/usr/bin/env python
"""Generate packages/shared-types from the Python domain package.

The frontend and the backend must agree on the wire contract exactly. Rather
than maintain TypeScript by hand and hope it keeps up, we emit it from the
Pydantic models and StrEnums that already define that contract.

    python scripts/generate_shared_types.py            # write
    python scripts/generate_shared_types.py --check    # fail if stale (CI)

tests/dataset/test_shared_types_current.py runs --check so drift is caught.
"""

from __future__ import annotations

import argparse
import sys
from enum import EnumMeta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

import mrittika_domain as domain  # noqa: E402
from mrittika_domain import enums as domain_enums  # noqa: E402
from mrittika_domain import records as domain_records  # noqa: E402
from pydantic import BaseModel  # noqa: E402

OUTPUT = REPO_ROOT / "packages" / "shared-types" / "src" / "generated.ts"

HEADER = """/**
 * GENERATED FILE -- DO NOT EDIT.
 *
 * Emitted from packages/domain (the Python source of truth) by
 * scripts/generate_shared_types.py. Edit the Pydantic models / StrEnums there
 * and regenerate; hand edits here will be overwritten and will fail CI.
 */

"""

#: JSON Schema primitive -> TypeScript primitive.
PRIMITIVES = {
    "string": "string",
    "number": "number",
    "integer": "number",
    "boolean": "boolean",
    "null": "null",
}


def ts_type(schema: dict, defs: dict) -> str:
    """Render one JSON Schema node as a TypeScript type expression."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]

    # Pydantic renders `X | None` as anyOf[X, null].
    if "anyOf" in schema:
        parts = [ts_type(s, defs) for s in schema["anyOf"]]
        # Collapse duplicates while preserving order.
        seen: list[str] = []
        for p in parts:
            if p not in seen:
                seen.append(p)
        return " | ".join(seen)

    kind = schema.get("type")
    if kind == "array":
        inner = ts_type(schema.get("items", {}), defs) if "items" in schema else "unknown"
        return f"{inner}[]"
    if kind == "object":
        return "Record<string, unknown>"
    if isinstance(kind, list):
        return " | ".join(PRIMITIVES.get(k, "unknown") for k in kind)
    if kind in PRIMITIVES:
        # A bare string with a format we don't model is still a string.
        return PRIMITIVES[kind]
    return "unknown"


def emit_enum(name: str, enum_cls: EnumMeta) -> str:
    """StrEnum -> TS string-literal union.

    A union rather than a TS `enum` so the values are structurally comparable
    with whatever the API actually sends, and so no runtime import is needed.
    """
    members = "\n".join(f"  | '{m.value}'" for m in enum_cls)
    return f"export type {name} =\n{members};\n"


def emit_interface(name: str, schema: dict, defs: dict) -> str:
    """Pydantic model JSON Schema -> TS interface."""
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop, prop_schema in schema.get("properties", {}).items():
        rendered = ts_type(prop_schema, defs)
        # Optional in the TS sense when Pydantic gave it a default.
        optional = "" if prop in required else "?"
        # Drop a redundant `| null` when the key is already optional.
        if optional and rendered.endswith(" | null"):
            rendered = rendered[: -len(" | null")]
        description = prop_schema.get("description")
        if description:
            lines.append(f"  /** {description} */")
        lines.append(f"  {prop}{optional}: {rendered};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build() -> str:
    chunks = [HEADER]

    chunks.append("// ─── Controlled vocabularies (packages/domain/enums.py) ───\n")
    for enum_name in sorted(
        n for n in dir(domain_enums) if isinstance(getattr(domain_enums, n), EnumMeta)
    ):
        enum_cls = getattr(domain_enums, enum_name)
        if enum_cls.__module__ != domain_enums.__name__:
            continue
        chunks.append(emit_enum(enum_name, enum_cls))

    chunks.append("\n// ─── Record schema (packages/domain/records.py) ───\n")
    models = [
        n
        for n in dir(domain_records)
        if isinstance(getattr(domain_records, n), type)
        and issubclass(getattr(domain_records, n), BaseModel)
        and getattr(domain_records, n) is not BaseModel
        and getattr(domain_records, n).__module__ == domain_records.__name__
    ]

    emitted: set[str] = set()
    for model_name in sorted(models):
        model = getattr(domain_records, model_name)
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        defs = schema.get("$defs", {})
        # Emit nested definitions first so TS declaration order reads top-down.
        for def_name, def_schema in defs.items():
            if def_name in emitted or "enum" in def_schema:
                continue  # enums already emitted above
            emitted.add(def_name)
            chunks.append(emit_interface(def_name, def_schema, defs))
        if model_name not in emitted:
            emitted.add(model_name)
            chunks.append(emit_interface(model_name, schema, defs))

    chunks.append("\n// ─── Confidence banding (packages/domain/confidence.py) ───\n")
    chunks.append(
        f"export const HIGH_CONFIDENCE_THRESHOLD = {domain.HIGH_THRESHOLD};\n"
        f"export const MEDIUM_CONFIDENCE_THRESHOLD = {domain.MEDIUM_THRESHOLD};\n"
    )

    chunks.append("\n// ─── Document state machine (packages/domain/state_machine.py) ───\n")
    transitions = ",\n".join(
        f"  {state.value}: [{', '.join(sorted(repr(t.value) for t in targets))}]"
        for state, targets in domain.ALLOWED_TRANSITIONS.items()
    )
    chunks.append(
        "export const ALLOWED_TRANSITIONS: Record<DocumentState, DocumentState[]> = {\n"
        f"{transitions}\n}};\n"
    )

    return "\n".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed file is out of date",
    )
    args = parser.parse_args()

    content = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    if args.check:
        if not OUTPUT.exists():
            print(f"MISSING: {OUTPUT.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        if OUTPUT.read_text() != content:
            print(
                f"STALE: {OUTPUT.relative_to(REPO_ROOT)} is out of date.\n"
                "Run: python scripts/generate_shared_types.py",
                file=sys.stderr,
            )
            return 1
        print(f"up to date: {OUTPUT.relative_to(REPO_ROOT)}")
        return 0

    OUTPUT.write_text(content)
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
