from __future__ import annotations

from typing import Literal

from api.schemas import EvaluationResponse

SummaryFormat = Literal["json", "markdown"]


def build_report_summary(report: EvaluationResponse) -> dict[str, object]:
    return {
        "report_id": report.report_id,
        "decision": report.decision,
        "policy": report.policy,
        "baseline_release_id": report.metadata.baseline_release_id,
        "candidate_release_id": report.metadata.candidate_release_id,
        "summary": report.summary,
        "failed_checks": report.evidence_summary.failed_checks,
        "failure_reasons": [check.reason for check in report.failed_checks],
        "failed_case_count": report.evidence_summary.failed_case_count,
        "total_case_count": report.evidence_summary.total_case_count,
        "critical_failure_count": report.evidence_summary.critical_failure_count,
        "failed_risk_categories": report.evidence_summary.failed_risk_categories,
    }


def format_markdown_summary(report: EvaluationResponse) -> str:
    summary = build_report_summary(report)
    lines = [
        "## EvalGate Report Summary",
        "",
        f"- Report: `{summary['report_id']}`",
        f"- Decision: `{summary['decision']}`",
        f"- Policy: `{summary['policy']}`",
        f"- Baseline: `{summary['baseline_release_id']}`",
        f"- Candidate: `{summary['candidate_release_id']}`",
        f"- Summary: {summary['summary']}",
        f"- Failed checks: {format_list(summary['failed_checks'])}",
        f"- Failed cases: {summary['failed_case_count']}/{summary['total_case_count']}",
        f"- Critical failures: {summary['critical_failure_count']}",
        f"- Risk categories: {format_list(summary['failed_risk_categories'])}",
    ]
    failure_reasons = summary["failure_reasons"]
    if isinstance(failure_reasons, list) and failure_reasons:
        lines.extend(["", "### Failure Reasons"])
        lines.extend(f"- {reason}" for reason in failure_reasons)
    else:
        lines.append("- Failure reasons: none")
    return "\n".join(lines)


def format_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    return ", ".join(f"`{value}`" for value in values)
