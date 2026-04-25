from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from api.schemas import EvaluationMetadata, EvaluationResponse
from evaluator.runner import evaluate_release
from policy.engine import evaluate_release_policy
from policy.profiles import load_policy_profile
from reporting import store


@dataclass(slots=True)
class EvaluationRun:
    response: EvaluationResponse
    report_path: Path


def run_evaluation(
    baseline_release_id: str,
    candidate_release_id: str,
    policy_name: str = "default",
) -> EvaluationRun:
    policy_profile = load_policy_profile(policy_name)
    baseline_metrics = evaluate_release(baseline_release_id)
    candidate_metrics = evaluate_release(candidate_release_id)
    decision = evaluate_release_policy(
        baseline=baseline_metrics,
        candidate=candidate_metrics,
        profile=policy_profile,
    )
    response = EvaluationResponse(
        report_id=decision.report_id,
        metadata=EvaluationMetadata(
            created_at=utc_now_isoformat(),
            baseline_release_id=baseline_release_id,
            candidate_release_id=candidate_release_id,
            policy=decision.policy,
            evalgate_version=get_evalgate_version(),
        ),
        policy=decision.policy,
        policy_thresholds=decision.policy_thresholds,
        decision=decision.decision,
        summary=decision.summary,
        checks=[asdict(check) for check in decision.checks],
        failed_checks=[asdict(check) for check in decision.failed_checks],
        baseline_metrics=decision.baseline_metrics,
        candidate_metrics=decision.candidate_metrics,
        deltas=decision.deltas,
    )
    report_path = store.save_report(response.report_id, response.model_dump())
    return EvaluationRun(response=response, report_path=report_path)


def utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def get_evalgate_version() -> str:
    try:
        return version("evalgate-ai")
    except PackageNotFoundError:
        return "0.0.0+unknown"
