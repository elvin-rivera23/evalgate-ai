from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from api.schemas import EvaluationResponse
from evalgate.errors import UnsupportedPolicyError
from evaluator.runner import evaluate_release
from policy.engine import evaluate_release_policy
from reporting import store

SUPPORTED_POLICIES = {"default"}


@dataclass(slots=True)
class EvaluationRun:
    response: EvaluationResponse
    report_path: Path


def run_evaluation(
    baseline_release_id: str,
    candidate_release_id: str,
    policy_name: str = "default",
) -> EvaluationRun:
    if policy_name not in SUPPORTED_POLICIES:
        raise UnsupportedPolicyError(policy_name)

    baseline_metrics = evaluate_release(baseline_release_id)
    candidate_metrics = evaluate_release(candidate_release_id)
    decision = evaluate_release_policy(
        baseline=baseline_metrics,
        candidate=candidate_metrics,
    )
    response = EvaluationResponse(
        report_id=decision.report_id,
        decision=decision.decision,
        summary=decision.summary,
        failed_checks=[asdict(check) for check in decision.failed_checks],
        baseline_metrics=decision.baseline_metrics,
        candidate_metrics=decision.candidate_metrics,
        deltas=decision.deltas,
    )
    report_path = store.save_report(response.report_id, response.model_dump())
    return EvaluationRun(response=response, report_path=report_path)
