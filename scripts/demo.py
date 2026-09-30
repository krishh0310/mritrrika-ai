"""Run the existing end-to-end record lifecycle in a browser.

Start and seed the stack as described in README.md first. Playwright must be
installed through `npm install` and `npx playwright install`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> None:
    """Exercise upload, verification, approval, and citizen views."""
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["npm", "run", "e2e", "--", "tests/e2e/lifecycle.spec.ts"],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    main()
