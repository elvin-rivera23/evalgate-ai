from __future__ import annotations

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evalgate.errors import ServiceAdapterError, UnknownReleaseError
from evaluator.fixtures import EvalCase
from evaluator.models import ServiceRunResult
from services.registry import ReleaseDefinition, get_release_definition


class InferenceService(Protocol):
    def infer(self, case: EvalCase) -> ServiceRunResult:
        """Run inference for one evaluation case."""


class DeterministicReleaseService:
    def __init__(self, release_id: str) -> None:
        self.release = get_release_definition(release_id)

    def infer(self, case: EvalCase) -> ServiceRunResult:
        payload = self.release.responses.get(case.case_id)
        if payload is None:
            raise UnknownReleaseError(case.case_id)

        return ServiceRunResult(
            case_id=case.case_id,
            latency_ms=payload.latency_ms,
            cost_units=payload.cost_units,
            answer=payload.answer,
            is_error=False,
        )


class HttpReleaseService:
    def __init__(self, release: ReleaseDefinition) -> None:
        if release.endpoint is None:
            raise ServiceAdapterError(release.release_id, "HTTP endpoint is required.")
        self.release = release

    def infer(self, case: EvalCase) -> ServiceRunResult:
        request_payload = {
            "release_id": self.release.release_id,
            "case_id": case.case_id,
            "risk_category": case.risk_category,
            "severity": case.severity,
            "prompt": case.prompt,
            "expected_answer": case.expected_answer,
        }
        request = Request(
            self.release.endpoint or "",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.release.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ServiceAdapterError(
                self.release.release_id,
                f"HTTP {exc.code} for case {case.case_id}.",
            ) from exc
        except URLError as exc:
            raise ServiceAdapterError(
                self.release.release_id,
                f"request failed for case {case.case_id}: {exc.reason}",
            ) from exc
        except json.JSONDecodeError as exc:
            raise ServiceAdapterError(
                self.release.release_id,
                f"invalid JSON response for case {case.case_id}.",
            ) from exc

        return build_http_result(self.release.release_id, case.case_id, response_payload)


def build_http_result(
    release_id: str,
    case_id: str,
    payload: object,
) -> ServiceRunResult:
    if not isinstance(payload, dict):
        raise ServiceAdapterError(release_id, f"response for case {case_id} must be an object.")

    try:
        answer = payload["answer"]
        latency_ms = payload["latency_ms"]
        cost_units = payload["cost_units"]
    except KeyError as exc:
        raise ServiceAdapterError(
            release_id,
            f"response for case {case_id} is missing {exc.args[0]}.",
        ) from exc

    if not isinstance(answer, str) or not answer:
        raise ServiceAdapterError(release_id, f"response for case {case_id} has invalid answer.")

    try:
        latency_value = float(latency_ms)
        cost_value = float(cost_units)
    except (TypeError, ValueError) as exc:
        raise ServiceAdapterError(
            release_id,
            f"response for case {case_id} has invalid numeric metrics.",
        ) from exc

    is_error = payload.get("is_error", False)
    if not isinstance(is_error, bool):
        raise ServiceAdapterError(release_id, f"response for case {case_id} has invalid is_error.")

    return ServiceRunResult(
        case_id=case_id,
        latency_ms=latency_value,
        cost_units=cost_value,
        answer=answer,
        is_error=is_error,
    )


def get_inference_service(release_id: str) -> InferenceService:
    release = get_release_definition(release_id)
    if release.adapter == "http":
        return HttpReleaseService(release)
    return DeterministicReleaseService(release_id)
