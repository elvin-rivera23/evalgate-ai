from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORT_ID_PATTERN = re.compile(r"^eval-[a-f0-9]{12}$")


def build_report_path(report_id: str) -> Path:
    if not REPORT_ID_PATTERN.fullmatch(report_id):
        raise ValueError(f"Invalid report_id: {report_id}")

    reports_dir = REPORTS_DIR.resolve()
    report_path = (reports_dir / f"{report_id}.json").resolve()
    if report_path.parent != reports_dir:
        raise ValueError(f"Invalid report path for report_id: {report_id}")
    return report_path


def save_report(report_id: str, payload: dict[str, object]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = build_report_path(report_id)
    fd, temp_path = tempfile.mkstemp(dir=REPORTS_DIR, prefix=f"{report_id}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, report_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return report_path
