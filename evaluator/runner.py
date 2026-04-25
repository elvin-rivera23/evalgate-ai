from __future__ import annotations

from dataclasses import asdict
from math import ceil

from fastapi.testclient import TestClient

from evaluator.fixtures import load_eval_cases
from evaluator.models import EvaluationMetrics, ReleaseEvaluation, ServiceRunResult
from services.apps import get_service_app


def evaluate_release(release_id: str) -> EvaluationMetrics:
    return evaluate_release_with_results(release_id).metrics


def evaluate_release_with_results(release_id: str) -> ReleaseEvaluation:
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
                case_id=case.case_id,
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

    metrics = EvaluationMetrics(
        latency_p95_ms=calculate_p95(latencies),
        error_rate=sum(error_hits) / len(error_hits),
        quality_score=sum(quality_hits) / len(quality_hits),
        cost_proxy=sum(cost_units) / len(cost_units),
    )
    return ReleaseEvaluation(metrics=metrics, results=results)


def metrics_to_dict(metrics: EvaluationMetrics) -> dict[str, float]:
    return asdict(metrics)


def calculate_p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = ceil(0.95 * len(ordered)) - 1
    return ordered[index]
