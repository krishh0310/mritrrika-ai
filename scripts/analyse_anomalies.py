#!/usr/bin/env python
"""Run the anomaly engine over the whole cadastre (§34).

Batch rather than per-document because the Isolation Forest is fitted on the
corpus: "unusual" is only definable relative to what else exists. The per-
document pass in pipeline_service reuses the same rules for one parcel.

    .venv/bin/python scripts/analyse_anomalies.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from app.db import SessionLocal  # noqa: E402
from app.services import anomaly_service  # noqa: E402


def main() -> int:
    with SessionLocal() as session:
        summary = anomaly_service.analyse_all(session)

    print(json.dumps(summary, indent=2))
    if summary["detector"] is None:
        # Not an error: §82 says the system runs without the optional model.
        print(
            f"\nIsolation Forest not used ({summary['detector_status']}). "
            "Rule findings above are complete on their own.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
