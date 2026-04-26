from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from api.schemas import EvaluationResponse


class ReportValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Report validation failed.")


def get_report_schema() -> dict[str, Any]:
    return EvaluationResponse.model_json_schema()


def validate_report_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportValidationError([f"Could not read report: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise ReportValidationError([f"Invalid JSON: {exc.msg} at line {exc.lineno}."]) from exc

    validate_report_payload(payload)


def validate_report_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ReportValidationError(["Report must be a JSON object."])

    try:
        EvaluationResponse.model_validate(payload)
    except ValidationError as exc:
        raise ReportValidationError(format_validation_errors(exc)) from exc


def format_validation_errors(exc: ValidationError) -> list[str]:
    errors: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        errors.append(f"{location}: {error['msg']}")
    return errors
