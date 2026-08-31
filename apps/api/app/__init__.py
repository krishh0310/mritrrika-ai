"""Mrittika AI API package.

Adds the sibling in-repo packages to sys.path. They are imported rather than
duplicated so there is exactly one definition of the domain vocabulary
(packages/domain) and one implementation of the quality gate
(services/ai-worker) shared by the API and the Celery worker (§79).
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

for _path in (
    _REPO_ROOT / "packages" / "domain",
    _REPO_ROOT / "services" / "ai-worker",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
