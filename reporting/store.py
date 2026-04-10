from __future__ import annotations

import json
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def save_report(report_id: str, payload: dict[str, object]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{report_id}.json"
    report_path.write_text(json.dumps(payload, indent=2) + "\n")
    return report_path
