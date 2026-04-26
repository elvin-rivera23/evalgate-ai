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
    reason: str | None


@dataclass(slots=True)
class FailedCheck:
    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: str
    reason: str


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
            status=check.status,
            reason=check.reason or "",
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
    return [
        build_upper_bound_check(
            metric="latency_p95_ms",
            baseline_value=baseline.latency_p95_ms,
            candidate_value=candidate.latency_p95_ms,
            threshold_type="max_increase_percent",
            threshold_value=thresholds.max_latency_increase_pct,
            delta=deltas["latency_p95_ms"],
            unit="percent",
            direction="increased",
        ),
        build_upper_bound_check(
            metric="error_rate",
            baseline_value=baseline.error_rate,
            candidate_value=candidate.error_rate,
            threshold_type="max_increase_absolute",
            threshold_value=thresholds.max_error_rate_increase_abs,
            delta=deltas["error_rate"],
            unit="absolute",
            direction="increased",
        ),
        build_lower_bound_check(
            metric="quality_score",
            baseline_value=baseline.quality_score,
            candidate_value=candidate.quality_score,
            threshold_type="max_drop_percent",
            threshold_value=thresholds.max_quality_drop_pct,
            delta=deltas["quality_score"],
            lower_bound=-thresholds.max_quality_drop_pct,
        ),
        build_upper_bound_check(
            metric="cost_proxy",
            baseline_value=baseline.cost_proxy,
            candidate_value=candidate.cost_proxy,
            threshold_type="max_increase_percent",
            threshold_value=thresholds.max_cost_increase_pct,
            delta=deltas["cost_proxy"],
            unit="percent",
            direction="increased",
        ),
    ]


def build_upper_bound_check(
    metric: str,
    baseline_value: float,
    candidate_value: float,
    threshold_type: str,
    threshold_value: float,
    delta: float,
    unit: str,
    direction: str,
) -> PolicyCheck:
    status = check_upper_bound(delta, threshold_value)
    return PolicyCheck(
        metric=metric,
        baseline=baseline_value,
        candidate=candidate_value,
        threshold_type=threshold_type,
        threshold_value=threshold_value,
        delta=delta,
        status=status,
        reason=(
            build_upper_bound_reason(
                metric=metric,
                baseline_value=baseline_value,
                candidate_value=candidate_value,
                threshold_value=threshold_value,
                delta=delta,
                unit=unit,
                direction=direction,
            )
            if status == "failed"
            else None
        ),
    )


def build_lower_bound_check(
    metric: str,
    baseline_value: float,
    candidate_value: float,
    threshold_type: str,
    threshold_value: float,
    delta: float,
    lower_bound: float,
) -> PolicyCheck:
    status = check_lower_bound(delta, lower_bound)
    return PolicyCheck(
        metric=metric,
        baseline=baseline_value,
        candidate=candidate_value,
        threshold_type=threshold_type,
        threshold_value=threshold_value,
        delta=delta,
        status=status,
        reason=(
            build_quality_reason(
                baseline_value=baseline_value,
                candidate_value=candidate_value,
                threshold_value=threshold_value,
                delta=delta,
            )
            if status == "failed"
            else None
        ),
    )


def build_upper_bound_reason(
    metric: str,
    baseline_value: float,
    candidate_value: float,
    threshold_value: float,
    delta: float,
    unit: str,
    direction: str,
) -> str:
    if unit == "percent":
        return (
            f"{metric} {direction} by {format_percent(delta)} from "
            f"{format_number(baseline_value)} to {format_number(candidate_value)}, "
            f"exceeding the allowed {format_percent(threshold_value)} increase."
        )

    return (
        f"{metric} {direction} by {format_number(delta)} from "
        f"{format_number(baseline_value)} to {format_number(candidate_value)}, "
        f"exceeding the allowed {format_number(threshold_value)} absolute increase."
    )


def build_quality_reason(
    baseline_value: float,
    candidate_value: float,
    threshold_value: float,
    delta: float,
) -> str:
    return (
        f"quality_score dropped by {format_percent(abs(delta))} from "
        f"{format_number(baseline_value)} to {format_number(candidate_value)}, "
        f"exceeding the allowed {format_percent(threshold_value)} drop."
    )


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_number(value: float) -> str:
    return f"{value:.4g}"


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
