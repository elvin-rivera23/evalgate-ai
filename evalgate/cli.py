from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from evalgate.errors import EvalGateError
from evalgate.orchestration import run_evaluation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalgate",
        description="Evaluate a candidate release against a baseline release.",
    )
    parser.add_argument("--baseline", required=True, help="Trusted baseline release ID.")
    parser.add_argument("--candidate", required=True, help="Candidate release ID.")
    parser.add_argument(
        "--policy",
        default="default",
        help="Policy name to apply. Only 'default' is currently supported.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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


def format_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


if __name__ == "__main__":
    raise SystemExit(main())
