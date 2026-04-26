from __future__ import annotations

from dataclasses import asdict
from math import ceil
from pathlib import Path

from evaluator.fixtures import load_eval_cases
from evaluator.models import EvaluationMetrics, ReleaseEvaluation, ServiceRunResult
from services.adapters import InferenceService, get_inference_service


def evaluate_release(
    release_id: str,
    config_dir: str | Path | None = None,
) -> EvaluationMetrics:
    return evaluate_release_with_results(release_id, config_dir=config_dir).metrics


def evaluate_release_with_results(
    release_id: str,
    service: InferenceService | None = None,
    config_dir: str | Path | None = None,
) -> ReleaseEvaluation:
    service = service or get_inference_service(release_id, config_dir)
    cases = load_eval_cases(config_dir)
    results: list[ServiceRunResult] = []

    for case in cases:
        results.append(service.infer(case))

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
