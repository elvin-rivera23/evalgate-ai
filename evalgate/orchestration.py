from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from api.schemas import CaseResult, EvaluationMetadata, EvaluationResponse, EvidenceSummary
from evaluator.fixtures import EvalCase, load_eval_cases
from evaluator.models import ServiceRunResult
from evaluator.runner import evaluate_release_with_results
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
    config_dir: str | Path | None = None,
) -> EvaluationRun:
    policy_profile = load_policy_profile(policy_name, config_dir)
    baseline_evaluation = evaluate_release_with_results(
        baseline_release_id,
        config_dir=config_dir,
    )
    candidate_evaluation = evaluate_release_with_results(
        candidate_release_id,
        config_dir=config_dir,
    )
    decision = evaluate_release_policy(
        baseline=baseline_evaluation.metrics,
        candidate=candidate_evaluation.metrics,
        profile=policy_profile,
    )
    case_results = build_case_results(
        baseline_results=baseline_evaluation.results,
        candidate_results=candidate_evaluation.results,
        config_dir=config_dir,
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
        evidence_summary=build_evidence_summary(
            failed_checks=[check.metric for check in decision.failed_checks],
            case_results=case_results,
        ),
        case_results=case_results,
        baseline_metrics=decision.baseline_metrics,
        candidate_metrics=decision.candidate_metrics,
        deltas=decision.deltas,
    )
    report_path = store.save_report(response.report_id, response.model_dump())
    return EvaluationRun(response=response, report_path=report_path)


def build_evidence_summary(
    failed_checks: list[str],
    case_results: list[CaseResult],
) -> EvidenceSummary:
    failed_cases = [case for case in case_results if not case.passed]
    return EvidenceSummary(
        failed_checks=failed_checks,
        failed_case_count=len(failed_cases),
        total_case_count=len(case_results),
        critical_failure_count=sum(1 for case in failed_cases if case.severity == "critical"),
        failed_risk_categories=sorted({case.risk_category for case in failed_cases}),
        max_latency_delta_ms=max((case.latency_delta_ms for case in case_results), default=0.0),
        max_cost_delta_units=max((case.cost_delta_units for case in case_results), default=0.0),
    )


def build_case_results(
    baseline_results: list[ServiceRunResult],
    candidate_results: list[ServiceRunResult],
    config_dir: str | Path | None = None,
) -> list[CaseResult]:
    cases_by_id = {case.case_id: case for case in load_eval_cases(config_dir)}
    baseline_by_id = {result.case_id: result for result in baseline_results}
    candidate_by_id = {result.case_id: result for result in candidate_results}

    return [
        build_case_result(
            case=case,
            baseline=baseline_by_id[case.case_id],
            candidate=candidate_by_id[case.case_id],
        )
        for case in cases_by_id.values()
    ]


def build_case_result(
    case: EvalCase,
    baseline: ServiceRunResult,
    candidate: ServiceRunResult,
) -> CaseResult:
    return CaseResult(
        case_id=case.case_id,
        risk_category=case.risk_category,
        severity=case.severity,
        expected_answer=case.expected_answer,
        baseline_answer=baseline.answer,
        candidate_answer=candidate.answer,
        passed=candidate.answer == case.expected_answer,
        baseline_latency_ms=baseline.latency_ms,
        candidate_latency_ms=candidate.latency_ms,
        latency_delta_ms=candidate.latency_ms - baseline.latency_ms,
        baseline_cost_units=baseline.cost_units,
        candidate_cost_units=candidate.cost_units,
        cost_delta_units=candidate.cost_units - baseline.cost_units,
    )


def utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def get_evalgate_version() -> str:
    try:
        return version("evalgate-ai")
    except PackageNotFoundError:
        return "0.0.0+unknown"
