from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evalgate.errors import EvalGateError
from evalgate.orchestration import run_evaluation
from evalgate.report_summary import SummaryFormat, build_report_summary, format_markdown_summary
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
        "--validate-config",
        action="store_true",
        help="Validate EvalGate fixture, release, and policy configuration.",
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
        "--show-report",
        metavar="REPORT_ID",
        help="Show one indexed EvalGate report entry by report ID.",
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
        return run_config_validation()

    if args.list_reports:
        return run_list_reports()

    if args.show_report:
        return run_show_report(args.show_report)

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


def run_config_validation() -> int:
    try:
        validate_config_or_raise()
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


def run_list_reports() -> int:
    try:
        entries = store.load_report_index()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report index: invalid ({exc})", file=sys.stderr)
        return 2

    print(json.dumps({"reports": entries}, indent=2, sort_keys=True))
    return 0


def run_show_report(report_id: str) -> int:
    try:
        entries = store.load_report_index()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report index: invalid ({exc})", file=sys.stderr)
        return 2

    for entry in entries:
        if entry.get("report_id") == report_id:
            print(json.dumps(entry, indent=2, sort_keys=True))
            return 0

    print(f"report index: report not found: {report_id}", file=sys.stderr)
    return 2


def format_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


if __name__ == "__main__":
    raise SystemExit(main())
