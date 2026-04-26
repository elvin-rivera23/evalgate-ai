from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORT_ID_PATTERN = re.compile(r"^eval-[a-f0-9]{12}$")
INDEX_FILENAME = "index.json"


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
    update_report_index(payload)
    return report_path


def build_index_path() -> Path:
    reports_dir = REPORTS_DIR.resolve()
    return reports_dir / INDEX_FILENAME


def load_report_index() -> list[dict[str, object]]:
    index_path = build_index_path()
    if not index_path.exists():
        return []

    with index_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict) or not isinstance(payload.get("reports"), list):
        raise ValueError("Invalid report index format.")
    return payload["reports"]


def update_report_index(payload: dict[str, object]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    entries = [
        entry for entry in load_report_index() if entry.get("report_id") != payload["report_id"]
    ]
    entries.append(build_index_entry(payload))
    entries.sort(key=lambda entry: str(entry["created_at"]), reverse=True)
    save_index(entries)


def build_index_entry(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload["metadata"]
    evidence_summary = payload["evidence_summary"]
    if not isinstance(metadata, dict) or not isinstance(evidence_summary, dict):
        raise ValueError("Invalid report payload for indexing.")

    return {
        "report_id": payload["report_id"],
        "created_at": metadata["created_at"],
        "baseline_release_id": metadata["baseline_release_id"],
        "candidate_release_id": metadata["candidate_release_id"],
        "policy": payload["policy"],
        "decision": payload["decision"],
        "failed_checks": evidence_summary["failed_checks"],
        "failed_case_count": evidence_summary["failed_case_count"],
        "critical_failure_count": evidence_summary["critical_failure_count"],
    }


def save_index(entries: list[dict[str, object]]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    index_path = build_index_path()
    fd, temp_path = tempfile.mkstemp(dir=REPORTS_DIR, prefix="index-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"reports": entries}, handle, indent=2)
            handle.write("\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, index_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return index_path
