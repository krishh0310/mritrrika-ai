"""Fail if tracked source contains common credential formats or private keys."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"),
    "Google API key": re.compile(rb"\bAIza[A-Za-z0-9_-]{35}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def scan() -> list[tuple[str, int, str]]:
    """Scan versioned and new non-ignored files; local `.env` is ignored."""
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    ).split(b"\0")
    findings = []
    for raw_path in filter(None, paths):
        path = ROOT / raw_path.decode()
        try:
            data = path.read_bytes()
        except (OSError, UnicodeError):
            continue
        if b"\0" in data:
            continue
        for number, line in enumerate(data.splitlines(), 1):
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append((str(path.relative_to(ROOT)), number, kind))
    return findings


if __name__ == "__main__":
    issues = scan()
    for path, number, kind in issues:
        print(f"{path}:{number}: {kind}")
    print(f"{len(issues)} secret finding(s) in tracked files")
    raise SystemExit(bool(issues))
