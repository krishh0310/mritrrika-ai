"""Verify each declared concept maps to a real Python artifact."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = re.compile(r"`([^`:]+\.py)\s*:\s*([^`]+)`")


def names_in(path: Path) -> set[str]:
    """Return callable/class/assignment names, excluding comments and docstrings."""
    tree = ast.parse(path.read_text())
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                names.update(f"{node.name}.{member.name}" for member in node.body
                             if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)))
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def audit() -> tuple[int, list[str]]:
    """Check all rows in the mapping table and return count and missing symbols."""
    rows = [line for line in (ROOT / "docs" / "domain-mapping.md").read_text().splitlines()
            if line.startswith("| ") and "`" in line]
    missing = []
    for row in rows:
        concept = row.split("|")[1].strip()
        artifacts = ARTIFACT.findall(row)
        if not artifacts:
            missing.append(f"{concept}: no code artifact")
        for relative, symbols in artifacts:
            path = ROOT / relative.strip()
            if not path.is_file():
                missing.append(f"{concept}: missing {relative}")
                continue
            available = names_in(path)
            for symbol in symbols.split(","):
                name = re.match(r"[A-Za-z_][A-Za-z_0-9.]*", symbol.strip())
                if name is None or name.group() not in available:
                    missing.append(f"{concept}: {relative}:{symbol.strip()}")
    return len(rows), missing


if __name__ == "__main__":
    count, missing = audit()
    for item in missing:
        print(item)
    print(f"{count} declared concepts checked; {len(missing)} unverified artifacts")
    raise SystemExit(bool(missing))
