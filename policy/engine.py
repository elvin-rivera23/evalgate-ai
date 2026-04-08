from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from evaluator.models import EvaluationMetrics
from evaluator.runner import metrics_to_dict
from policy.models import PolicyThresholds


@dataclass(slots=True)
class FailedCheck:
    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: str = "failed"


@dataclass(slots=True)
class PolicyDecision:
    report_id: str
    decision: str
    summary: str
    failed_checks: list[FailedCheck]
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    deltas: dict[str, float]


def evaluate_release_policy(
    baseline: EvaluationMetrics,
    candidate: EvaluationMetrics,
    thresholds: PolicyThresholds | None = None,
) -> PolicyDecision:
    thresholds = thresholds or PolicyThresholds()
    baseline_metrics = metrics_to_dict(baseline)
    candidate_metrics = metrics_to_dict(candidate)
    deltas = build_deltas(baseline, candidate)
    failed_checks: list[FailedCheck] = []

    if deltas["latency_p95_ms"] > thresholds.max_latency_increase_pct:
        failed_checks.append(
            FailedCheck(
                metric="latency_p95_ms",
                baseline=baseline.latency_p95_ms,
                candidate=candidate.latency_p95_ms,
                threshold_type="max_increase_percent",
                threshold_value=thresholds.max_latency_increase_pct,
                delta=deltas["latency_p95_ms"],
            )
        )

    if deltas["error_rate"] > thresholds.max_error_rate_increase_abs:
        failed_checks.append(
            FailedCheck(
                metric="error_rate",
                baseline=baseline.error_rate,
                candidate=candidate.error_rate,
                threshold_type="max_increase_absolute",
                threshold_value=thresholds.max_error_rate_increase_abs,
                delta=deltas["error_rate"],
            )
        )

    if deltas["quality_score"] < (-1 * thresholds.max_quality_drop_pct):
        failed_checks.append(
            FailedCheck(
                metric="quality_score",
                baseline=baseline.quality_score,
                candidate=candidate.quality_score,
                threshold_type="max_drop_percent",
                threshold_value=thresholds.max_quality_drop_pct,
                delta=deltas["quality_score"],
            )
        )

    if deltas["cost_proxy"] > thresholds.max_cost_increase_pct:
        failed_checks.append(
            FailedCheck(
                metric="cost_proxy",
                baseline=baseline.cost_proxy,
                candidate=candidate.cost_proxy,
                threshold_type="max_increase_percent",
                threshold_value=thresholds.max_cost_increase_pct,
                delta=deltas["cost_proxy"],
            )
        )

    decision = "block" if failed_checks else "promote"
    summary = build_summary(decision, failed_checks)

    return PolicyDecision(
        report_id=f"eval-{uuid4().hex[:12]}",
        decision=decision,
        summary=summary,
        failed_checks=failed_checks,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        deltas=deltas,
    )


def build_deltas(
    baseline: EvaluationMetrics,
    candidate: EvaluationMetrics,
) -> dict[str, float]:
    return {
        "latency_p95_ms": safe_percent_change(
            baseline.latency_p95_ms,
            candidate.latency_p95_ms,
        ),
        "error_rate": candidate.error_rate - baseline.error_rate,
        "quality_score": safe_percent_change(
            baseline.quality_score,
            candidate.quality_score,
        ),
        "cost_proxy": safe_percent_change(
            baseline.cost_proxy,
            candidate.cost_proxy,
        ),
    }


def safe_percent_change(baseline_value: float, candidate_value: float) -> float:
    if baseline_value == 0:
        return 0.0
    return (candidate_value - baseline_value) / baseline_value


def build_summary(decision: str, failed_checks: list[FailedCheck]) -> str:
    if decision == "promote":
        return "Candidate is within the default release thresholds."

    failed_metrics = ", ".join(check.metric for check in failed_checks)
    return f"Candidate exceeded the default policy thresholds for: {failed_metrics}."
