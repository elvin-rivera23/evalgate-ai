from __future__ import annotations

from typing import Literal

from api.schemas import EvaluationResponse
from evalgate.report_summary import format_list

TriageFormat = Literal["json", "markdown"]


def build_failure_triage(report: EvaluationResponse) -> dict[str, object]:
    failed_cases = [case for case in report.case_results if not case.passed]
    return {
        "report_id": report.report_id,
        "decision": report.decision,
        "policy": report.policy,
        "baseline_release_id": report.metadata.baseline_release_id,
        "candidate_release_id": report.metadata.candidate_release_id,
        "summary": report.summary,
        "failed_check_count": len(report.failed_checks),
        "failed_case_count": report.evidence_summary.failed_case_count,
        "total_case_count": report.evidence_summary.total_case_count,
        "critical_failure_count": report.evidence_summary.critical_failure_count,
        "failed_risk_categories": report.evidence_summary.failed_risk_categories,
        "failed_checks": [
            {
                "metric": check.metric,
                "reason": check.reason,
                "baseline": check.baseline,
                "candidate": check.candidate,
                "delta": check.delta,
                "threshold_type": check.threshold_type,
                "threshold_value": check.threshold_value,
            }
            for check in report.failed_checks
        ],
        "failed_cases": [
            {
                "case_id": case.case_id,
                "risk_category": case.risk_category,
                "severity": case.severity,
                "expected_answer": case.expected_answer,
                "baseline_answer": case.baseline_answer,
                "candidate_answer": case.candidate_answer,
                "latency_delta_ms": case.latency_delta_ms,
                "cost_delta_units": case.cost_delta_units,
            }
            for case in failed_cases
        ],
    }


def format_markdown_triage(report: EvaluationResponse) -> str:
    triage = build_failure_triage(report)
    lines = [
        "## EvalGate Failure Triage",
        "",
        f"- Report: `{triage['report_id']}`",
        f"- Decision: `{triage['decision']}`",
        f"- Policy: `{triage['policy']}`",
        f"- Baseline: `{triage['baseline_release_id']}`",
        f"- Candidate: `{triage['candidate_release_id']}`",
        f"- Summary: {triage['summary']}",
        f"- Failed checks: {triage['failed_check_count']}",
        f"- Failed cases: {triage['failed_case_count']}/{triage['total_case_count']}",
        f"- Critical failures: {triage['critical_failure_count']}",
        f"- Risk categories: {format_list(triage['failed_risk_categories'])}",
    ]

    failed_checks = triage["failed_checks"]
    if isinstance(failed_checks, list) and failed_checks:
        lines.extend(["", "### Failed Checks"])
        for check in failed_checks:
            if isinstance(check, dict):
                lines.append(f"- `{check['metric']}`: {check['reason']}")
    else:
        lines.append("- Failed check details: none")

    failed_cases = triage["failed_cases"]
    if isinstance(failed_cases, list) and failed_cases:
        lines.extend(["", "### Failed Cases"])
        for case in failed_cases:
            if isinstance(case, dict):
                lines.append(
                    f"- `{case['case_id']}` "
                    f"({case['severity']}, {case['risk_category']}): "
                    f"expected `{case['expected_answer']}`, got `{case['candidate_answer']}`"
                )
    else:
        lines.append("- Failed case details: none")

    return "\n".join(lines)
