from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil

from fastapi.testclient import TestClient

from evaluator.fixtures import load_eval_cases
from evaluator.models import EvaluationMetrics
from services.apps import get_service_app


@dataclass(slots=True)
class ServiceRunResult:
    latency_ms: float
    cost_units: float
    answer: str
    is_error: bool


def evaluate_release(release_id: str) -> EvaluationMetrics:
    app = get_service_app(release_id)
    client = TestClient(app)
    cases = load_eval_cases()
    results: list[ServiceRunResult] = []

    for case in cases:
        response = client.post(
            "/infer",
            json={"case_id": case.case_id, "prompt": case.prompt},
        )
        payload = response.json()
        results.append(
            ServiceRunResult(
                latency_ms=payload["latency_ms"],
                cost_units=payload["cost_units"],
                answer=payload["answer"],
                is_error=response.status_code >= 400,
            )
        )

    latencies = [result.latency_ms for result in results]
    quality_hits = [
        1.0 if result.answer == case.expected_answer else 0.0
        for result, case in zip(results, cases, strict=True)
    ]
    error_hits = [1.0 if result.is_error else 0.0 for result in results]
    cost_units = [result.cost_units for result in results]

    return EvaluationMetrics(
        latency_p95_ms=calculate_p95(latencies),
        error_rate=sum(error_hits) / len(error_hits),
        quality_score=sum(quality_hits) / len(quality_hits),
        cost_proxy=sum(cost_units) / len(cost_units),
    )


def metrics_to_dict(metrics: EvaluationMetrics) -> dict[str, float]:
    return asdict(metrics)


def calculate_p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = ceil(0.95 * len(ordered)) - 1
    return ordered[index]
