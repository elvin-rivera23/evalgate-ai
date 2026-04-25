from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import uuid4

from evaluator.models import EvaluationMetrics
from evaluator.runner import metrics_to_dict
from policy.models import PolicyProfile, PolicyThresholds


@dataclass(slots=True)
class PolicyCheck:
    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: str


@dataclass(slots=True)
class FailedCheck(PolicyCheck):
    status: str = "failed"


@dataclass(slots=True)
class PolicyDecision:
    report_id: str
    policy: str
    policy_thresholds: dict[str, float]
    decision: str
    summary: str
    checks: list[PolicyCheck]
    failed_checks: list[FailedCheck]
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    deltas: dict[str, float]


def evaluate_release_policy(
    baseline: EvaluationMetrics,
    candidate: EvaluationMetrics,
    profile: PolicyProfile | None = None,
) -> PolicyDecision:
    profile = profile or PolicyProfile(
        name="default",
        description="Balanced release gate for general model-backed services.",
        thresholds=PolicyThresholds(),
    )
    thresholds = profile.thresholds
    baseline_metrics = metrics_to_dict(baseline)
    candidate_metrics = metrics_to_dict(candidate)
    deltas = build_deltas(baseline, candidate)
    checks = build_policy_checks(baseline, candidate, deltas, thresholds)
    failed_checks = [
        FailedCheck(
            metric=check.metric,
            baseline=check.baseline,
            candidate=check.candidate,
            threshold_type=check.threshold_type,
            threshold_value=check.threshold_value,
            delta=check.delta,
        )
        for check in checks
        if check.status == "failed"
    ]

    decision = "block" if failed_checks else "promote"
    summary = build_summary(profile.name, decision, failed_checks)

    return PolicyDecision(
        report_id=f"eval-{uuid4().hex[:12]}",
        policy=profile.name,
        policy_thresholds=asdict(thresholds),
        decision=decision,
        summary=summary,
        checks=checks,
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


def build_policy_checks(
    baseline: EvaluationMetrics,
    candidate: EvaluationMetrics,
    deltas: dict[str, float],
    thresholds: PolicyThresholds,
) -> list[PolicyCheck]:
    checks = [
        PolicyCheck(
            metric="latency_p95_ms",
            baseline=baseline.latency_p95_ms,
            candidate=candidate.latency_p95_ms,
            threshold_type="max_increase_percent",
            threshold_value=thresholds.max_latency_increase_pct,
            delta=deltas["latency_p95_ms"],
            status=check_upper_bound(deltas["latency_p95_ms"], thresholds.max_latency_increase_pct),
        ),
        PolicyCheck(
            metric="error_rate",
            baseline=baseline.error_rate,
            candidate=candidate.error_rate,
            threshold_type="max_increase_absolute",
            threshold_value=thresholds.max_error_rate_increase_abs,
            delta=deltas["error_rate"],
            status=check_upper_bound(deltas["error_rate"], thresholds.max_error_rate_increase_abs),
        ),
        PolicyCheck(
            metric="quality_score",
            baseline=baseline.quality_score,
            candidate=candidate.quality_score,
            threshold_type="max_drop_percent",
            threshold_value=thresholds.max_quality_drop_pct,
            delta=deltas["quality_score"],
            status=check_lower_bound(deltas["quality_score"], -thresholds.max_quality_drop_pct),
        ),
        PolicyCheck(
            metric="cost_proxy",
            baseline=baseline.cost_proxy,
            candidate=candidate.cost_proxy,
            threshold_type="max_increase_percent",
            threshold_value=thresholds.max_cost_increase_pct,
            delta=deltas["cost_proxy"],
            status=check_upper_bound(deltas["cost_proxy"], thresholds.max_cost_increase_pct),
        ),
    ]
    return checks


def check_upper_bound(value: float, threshold: float) -> str:
    return "failed" if value > threshold else "passed"


def check_lower_bound(value: float, threshold: float) -> str:
    return "failed" if value < threshold else "passed"


def safe_percent_change(baseline_value: float, candidate_value: float) -> float:
    if baseline_value == 0:
        return 0.0
    return (candidate_value - baseline_value) / baseline_value


def build_summary(policy_name: str, decision: str, failed_checks: list[FailedCheck]) -> str:
    if decision == "promote":
        return f"Candidate is within the {policy_name} release thresholds."

    failed_metrics = ", ".join(check.metric for check in failed_checks)
    return f"Candidate exceeded the {policy_name} policy thresholds for: {failed_metrics}."
