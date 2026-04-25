from __future__ import annotations

from typing import Protocol

from evalgate.errors import UnknownReleaseError
from evaluator.fixtures import EvalCase
from evaluator.models import ServiceRunResult
from services.registry import get_release_definition


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


def get_inference_service(release_id: str) -> InferenceService:
    return DeterministicReleaseService(release_id)
