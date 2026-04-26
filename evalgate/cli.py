from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from api.schemas import EvaluationResponse
from evalgate.errors import EvalGateError
from evalgate.orchestration import run_evaluation
from evalgate.report_summary import SummaryFormat, build_report_summary, format_markdown_summary
from evalgate.report_triage import build_failure_triage, format_markdown_triage
from evalgate.report_validation import (
    ReportValidationError,
    get_report_schema,
    load_report_file,
    validate_report_file,
)
from evalgate.validation import ConfigValidationError, validate_config_or_raise
from reporting import store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalgate",
        description="Evaluate a candidate release against a baseline release.",
    )
    parser.add_argument("--baseline", help="Trusted baseline release ID.")
    parser.add_argument("--candidate", help="Candidate release ID.")
    parser.add_argument(
        "--policy",
        default="default",
        help="Policy profile name to apply.",
    )
    parser.add_argument(
        "--config-dir",
        metavar="PATH",
        help=(
            "Directory containing fixtures/eval_cases.json, services/releases.json, "
            "and policy/profiles.json. Defaults to this repository or EVALGATE_CONFIG_DIR."
        ),
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate EvalGate fixture, release, and policy configuration.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the built-in passing and blocking EvalGate demo workflow.",
    )
    parser.add_argument(
        "--validate-report",
        metavar="PATH",
        help="Validate a persisted EvalGate JSON report against the report contract.",
    )
    parser.add_argument(
        "--print-report-schema",
        action="store_true",
        help="Print the EvalGate evaluation report JSON Schema.",
    )
    parser.add_argument(
        "--summarize-report",
        metavar="PATH",
        help="Summarize a persisted EvalGate JSON report.",
    )
    parser.add_argument(
        "--summary-format",
        choices=["json", "markdown"],
        default="json",
        help="Output format for --summarize-report.",
    )
    parser.add_argument(
        "--list-reports",
        action="store_true",
        help="List indexed EvalGate reports.",
    )
    parser.add_argument(
        "--report-candidate",
        metavar="RELEASE_ID",
        help="Filter --list-reports by candidate release ID.",
    )
    parser.add_argument(
        "--report-baseline",
        metavar="RELEASE_ID",
        help="Filter --list-reports by baseline release ID.",
    )
    parser.add_argument(
        "--report-policy",
        metavar="POLICY",
        help="Filter --list-reports by policy profile.",
    )
    parser.add_argument(
        "--report-decision",
        choices=["promote", "block"],
        help="Filter --list-reports by release decision.",
    )
    parser.add_argument(
        "--report-limit",
        type=int,
        metavar="COUNT",
        help="Limit the number of reports returned by --list-reports.",
    )
    parser.add_argument(
        "--show-report",
        metavar="REPORT_ID",
        help="Show a saved EvalGate JSON report by report ID.",
    )
    parser.add_argument(
        "--triage-report",
        metavar="REPORT_ID",
        help="Show failed checks and cases for a saved EvalGate report ID.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.print_report_schema:
        print(json.dumps(get_report_schema(), indent=2, sort_keys=True))
        return 0

    if args.validate_report:
        return run_report_validation(Path(args.validate_report))

    if args.summarize_report:
        return run_report_summary(Path(args.summarize_report), args.summary_format)

    if args.validate_config:
        return run_config_validation(args.config_dir)

    if args.demo:
        return run_demo(args.config_dir)

    if args.list_reports:
        return run_list_reports(
            candidate=args.report_candidate,
            baseline=args.report_baseline,
            policy=args.report_policy,
            decision=args.report_decision,
            limit=args.report_limit,
        )

    if args.show_report:
        return run_show_report(args.show_report)

    if args.triage_report:
        return run_report_triage(args.triage_report, args.summary_format)

    if not args.baseline or not args.candidate:
        print(
            "error: --baseline and --candidate are required unless a validation option is used.",
            file=sys.stderr,
        )
        return 2

    try:
        evaluation = run_evaluation(
            baseline_release_id=args.baseline,
            candidate_release_id=args.candidate,
            policy_name=args.policy,
            config_dir=args.config_dir,
        )
    except EvalGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"decision: {evaluation.response.decision}")
    print(f"policy: {evaluation.response.policy}")
    print(f"summary: {evaluation.response.summary}")
    print(f"failed checks: {format_list(evaluation.response.evidence_summary.failed_checks)}")
    print(
        "failed cases: "
        f"{evaluation.response.evidence_summary.failed_case_count}/"
        f"{evaluation.response.evidence_summary.total_case_count}"
    )
    print(f"critical failures: {evaluation.response.evidence_summary.critical_failure_count}")
    print(
        "risk categories: "
        f"{format_list(evaluation.response.evidence_summary.failed_risk_categories)}"
    )
    print(f"report: {evaluation.report_path}")
    return 0 if evaluation.response.decision == "promote" else 1


def run_demo(config_dir: str | Path | None = None) -> int:
    try:
        passing_run = run_evaluation(
            baseline_release_id="baseline",
            candidate_release_id="candidate-good",
            policy_name="default",
            config_dir=config_dir,
        )
        blocking_run = run_evaluation(
            baseline_release_id="baseline",
            candidate_release_id="candidate-bad",
            policy_name="default",
            config_dir=config_dir,
        )
    except EvalGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    history = filter_report_entries(
        store.load_report_index(),
        candidate="candidate-bad",
        decision="block",
        limit=3,
    )
    demo_output = {
        "passing_report_id": passing_run.response.report_id,
        "blocking_report_id": blocking_run.response.report_id,
        "blocked_candidate_history": history,
    }

    print("# EvalGate Demo")
    print()
    print("## Evaluations")
    print()
    print(
        "- Passing candidate: "
        f"`{passing_run.response.metadata.candidate_release_id}` -> "
        f"`{passing_run.response.decision}` "
        f"({passing_run.response.report_id})"
    )
    print(
        "- Blocking candidate: "
        f"`{blocking_run.response.metadata.candidate_release_id}` -> "
        f"`{blocking_run.response.decision}` "
        f"({blocking_run.response.report_id})"
    )
    print()
    print(format_markdown_summary(passing_run.response))
    print()
    print(format_markdown_triage(blocking_run.response))
    print()
    print("## Recent Blocked Candidate History")
    print()
    print(json.dumps(demo_output, indent=2, sort_keys=True))
    return 0


def run_config_validation(config_dir: str | Path | None = None) -> int:
    try:
        validate_config_or_raise(config_dir)
    except ConfigValidationError as exc:
        print("config: invalid", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    print("config: valid")
    return 0


def run_report_validation(path: Path) -> int:
    try:
        validate_report_file(path)
    except ReportValidationError as exc:
        print("report: invalid", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    print("report: valid")
    return 0


def run_report_summary(path: Path, output_format: SummaryFormat) -> int:
    try:
        report = load_report_file(path)
    except ReportValidationError as exc:
        print("report: invalid", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    if output_format == "markdown":
        print(format_markdown_summary(report))
    else:
        print(json.dumps(build_report_summary(report), indent=2, sort_keys=True))
    return 0


def run_list_reports(
    candidate: str | None = None,
    baseline: str | None = None,
    policy: str | None = None,
    decision: str | None = None,
    limit: int | None = None,
) -> int:
    if limit is not None and limit < 1:
        print("report index: --report-limit must be greater than 0", file=sys.stderr)
        return 2

    try:
        entries = store.load_report_index()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report index: invalid ({exc})", file=sys.stderr)
        return 2

    filtered_entries = filter_report_entries(
        entries,
        candidate=candidate,
        baseline=baseline,
        policy=policy,
        decision=decision,
        limit=limit,
    )
    print(json.dumps({"reports": filtered_entries}, indent=2, sort_keys=True))
    return 0


def filter_report_entries(
    entries: list[dict[str, object]],
    *,
    candidate: str | None = None,
    baseline: str | None = None,
    policy: str | None = None,
    decision: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    filtered_entries = []
    for entry in entries:
        if candidate is not None and entry.get("candidate_release_id") != candidate:
            continue
        if baseline is not None and entry.get("baseline_release_id") != baseline:
            continue
        if policy is not None and entry.get("policy") != policy:
            continue
        if decision is not None and entry.get("decision") != decision:
            continue
        filtered_entries.append(entry)

    if limit is not None:
        return filtered_entries[:limit]
    return filtered_entries


def run_show_report(report_id: str) -> int:
    try:
        report = load_report_by_id(report_id)
    except ReportLookupError as exc:
        print(exc, file=sys.stderr)
        return 2
    except ReportValidationError as exc:
        print("report: invalid", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def run_report_triage(report_id: str, output_format: SummaryFormat) -> int:
    try:
        report = load_report_by_id(report_id)
    except ReportLookupError as exc:
        print(exc, file=sys.stderr)
        return 2
    except ReportValidationError as exc:
        print("report: invalid", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    if output_format == "markdown":
        print(format_markdown_triage(report))
    else:
        print(json.dumps(build_failure_triage(report), indent=2, sort_keys=True))
    return 0


class ReportLookupError(Exception):
    pass


def load_report_by_id(report_id: str) -> EvaluationResponse:
    try:
        report_path = store.build_report_path(report_id)
    except ValueError as exc:
        raise ReportLookupError(f"report: invalid id ({exc})") from exc

    try:
        entries = store.load_report_index()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ReportLookupError(f"report index: invalid ({exc})") from exc

    if report_path.exists():
        return load_report_file(report_path)

    for entry in entries:
        if entry.get("report_id") == report_id:
            raise ReportLookupError(f"report artifact: missing for indexed report: {report_path}")

    raise ReportLookupError(f"report index: report not found: {report_id}")


def format_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


if __name__ == "__main__":
    raise SystemExit(main())
