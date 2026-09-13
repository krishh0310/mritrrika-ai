#!/usr/bin/env python
"""Check the UI message catalogues (§14).

    python scripts/check_i18n.py

Key parity is already a TYPE error: hi.ts declares itself
`Record<MessageKey, string>`, so a missing key fails `tsc --noEmit` and an
extra key fails as an excess property. That check runs in CI and is stronger
than anything this script could do, because it cannot be skipped.

So this script checks what the type system cannot see:

  * an empty translation, which types fine and renders as nothing
  * a Hindi value byte-identical to the English one -- the signature of a key
    that was copied across and never translated
  * a duplicate key, which TypeScript reports only as TS1117 at the second
    occurrence and is easy to miss in a large diff

Parity is verified here too, so the script is useful on its own in a pre-commit
hook where tsc may not have run.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MESSAGES = REPO_ROOT / "packages" / "ui" / "src" / "messages"

#: Values that are correctly the same in both catalogues. The language names
#: are each written in their OWN language on purpose: a switcher that labels
#: हिन्दी only in English is useless to the reader who needs it.
SAME_BY_DESIGN = {"lang.english", "lang.hindi"}

ENTRY = re.compile(r'^\s*"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$', re.M)


def parse(path: Path) -> tuple[dict[str, str], list[str]]:
    if not path.exists():
        raise SystemExit(f"missing catalogue {path}")
    text = path.read_text(encoding="utf-8")
    pairs = ENTRY.findall(text)
    keys = [k for k, _ in pairs]
    return dict(pairs), keys


def main() -> int:
    en, en_keys = parse(MESSAGES / "en.ts")
    hi, hi_keys = parse(MESSAGES / "hi.ts")
    problems: list[str] = []

    for name, keys in (("en", en_keys), ("hi", hi_keys)):
        for key, count in Counter(keys).items():
            if count > 1:
                problems.append(f"{name}.ts: duplicate key {key!r} ({count} times)")

    for key in sorted(set(en) - set(hi)):
        problems.append(f"hi.ts: missing key {key!r}")
    for key in sorted(set(hi) - set(en)):
        problems.append(f"hi.ts: key {key!r} is not in en.ts")

    for key, value in sorted(hi.items()):
        if not value.strip():
            problems.append(f"hi.ts: {key!r} is empty")
        elif key in en and value == en[key] and key not in SAME_BY_DESIGN:
            problems.append(
                f"hi.ts: {key!r} is identical to English ({value!r}) -- untranslated?"
            )

    for key, value in sorted(en.items()):
        if not value.strip():
            problems.append(f"en.ts: {key!r} is empty")

    if problems:
        print(f"{len(problems)} problem(s) in the message catalogues:\n")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(f"message catalogues OK: {len(en)} keys, en + hi in parity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
