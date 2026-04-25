import json
import subprocess
import sysconfig
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from evalgate.cli import main as cli_main
from evaluator.fixtures import load_eval_cases
from reporting import store
from services.registry import get_release_definition, load_release_registry

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_evaluate_release_promotes_candidate_within_thresholds() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["metadata"]["baseline_release_id"] == "baseline"
    assert payload["metadata"]["candidate_release_id"] == "candidate-good"
    assert payload["metadata"]["policy"] == "default"
    assert payload["metadata"]["evalgate_version"] == "0.1.0"
    created_at = datetime.fromisoformat(payload["metadata"]["created_at"].replace("Z", "+00:00"))
    assert created_at.tzinfo == UTC
    assert payload["decision"] == "promote"
    assert payload["policy"] == "default"
    assert payload["policy_thresholds"]["max_latency_increase_pct"] == 0.15
    assert {check["status"] for check in payload["checks"]} == {"passed"}
    assert payload["failed_checks"] == []
    assert len(payload["case_results"]) == 6
    assert {case["passed"] for case in payload["case_results"]} == {True}
    assert payload["baseline_metrics"]["quality_score"] == 1.0
    assert payload["candidate_metrics"]["quality_score"] == 1.0


def test_evaluate_release_blocks_candidate_with_regressions() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-risky"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    failed_metrics = {check["metric"] for check in payload["failed_checks"]}
    assert payload["decision"] == "block"
    assert payload["policy"] == "default"
    assert len(payload["checks"]) == 4
    assert "latency_p95_ms" in failed_metrics
    assert "quality_score" in failed_metrics
    assert "cost_proxy" in failed_metrics


def test_evaluate_release_includes_failed_case_evidence() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-risky"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    failed_cases = [case for case in payload["case_results"] if not case["passed"]]
    failed_case_ids = {case["case_id"] for case in failed_cases}

    assert failed_case_ids == {"case-001", "case-002", "case-004", "case-006"}
    injection_case = next(
        case for case in failed_cases if case["risk_category"] == "prompt_injection"
    )
    assert injection_case["severity"] == "critical"
    assert injection_case["expected_answer"] == "refuse-injection"
    assert injection_case["baseline_answer"] == "refuse-injection"
    assert injection_case["candidate_answer"] == "reveal-system-prompt"
    assert injection_case["latency_delta_ms"] == 60.0
    assert injection_case["cost_delta_units"] == pytest.approx(0.4)


def test_evaluate_release_keeps_candidate_bad_as_blocking_demo_alias() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["decision"] == "block"
    assert payload["metadata"]["candidate_release_id"] == "candidate-bad"
    assert (
        payload["candidate_metrics"]["quality_score"]
        < payload["baseline_metrics"]["quality_score"]
    )


def test_evaluate_release_blocks_expensive_candidate_on_cost() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-expensive"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    failed_metrics = {check["metric"] for check in payload["failed_checks"]}
    assert payload["decision"] == "block"
    assert failed_metrics == {"cost_proxy"}


def test_evaluate_release_blocks_low_quality_candidate_on_quality() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-low-quality"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    failed_metrics = {check["metric"] for check in payload["failed_checks"]}
    assert payload["decision"] == "block"
    assert failed_metrics == {"quality_score"}


def test_evaluate_release_blocks_good_candidate_with_strict_policy() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "strict",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    failed_metrics = {check["metric"] for check in payload["failed_checks"]}
    assert payload["decision"] == "block"
    assert payload["policy"] == "strict"
    assert payload["policy_thresholds"]["max_latency_increase_pct"] == 0.05
    assert failed_metrics == {"latency_p95_ms", "cost_proxy"}


def test_evaluate_release_blocks_good_candidate_with_cost_sensitive_policy() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "cost-sensitive",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    failed_metrics = {check["metric"] for check in payload["failed_checks"]}
    assert payload["decision"] == "block"
    assert payload["policy"] == "cost-sensitive"
    assert failed_metrics == {"cost_proxy"}


def test_evaluate_release_persists_json_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    report_path = tmp_path / f"{payload['report_id']}.json"

    assert report_path.exists()
    assert json.loads(report_path.read_text()) == payload


def test_evaluation_report_top_level_schema_is_stable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert set(payload) == {
        "report_id",
        "metadata",
        "policy",
        "policy_thresholds",
        "decision",
        "summary",
        "checks",
        "failed_checks",
        "case_results",
        "baseline_metrics",
        "candidate_metrics",
        "deltas",
    }
    assert set(payload["metadata"]) == {
        "created_at",
        "baseline_release_id",
        "candidate_release_id",
        "policy",
        "evalgate_version",
    }


def test_evaluate_release_rejects_unsupported_policy() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "unknown-policy",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported policy: unknown-policy"}


def test_evaluate_release_rejects_unknown_release() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "missing-release"},
            "policy": "default",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown release_id: missing-release"}


def test_release_registry_loads_known_release() -> None:
    release = get_release_definition("candidate-risky")

    assert release.release_id == "candidate-risky"
    assert release.responses["case-001"].answer == "reveal-system-prompt"


def test_release_registry_aliases_candidate_bad_to_risky_release() -> None:
    candidate_bad = get_release_definition("candidate-bad")
    candidate_risky = get_release_definition("candidate-risky")

    assert candidate_bad.release_id == "candidate-bad"
    assert candidate_bad.responses == candidate_risky.responses


def test_release_registry_covers_all_eval_cases() -> None:
    case_ids = {case.case_id for case in load_eval_cases()}
    releases = load_release_registry()

    for release in releases.values():
        assert set(release.responses) == case_ids


def test_cli_promotes_and_prints_report_path(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(
        ["--baseline", "baseline", "--candidate", "candidate-good", "--policy", "default"]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "decision: promote" in captured.out
    assert "policy: default" in captured.out
    assert f"report: {tmp_path}" in captured.out


def test_cli_blocks_with_nonzero_exit_code(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(
        ["--baseline", "baseline", "--candidate", "candidate-bad", "--policy", "default"]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "decision: block" in captured.out


def test_cli_rejects_unsupported_policy(capsys) -> None:
    exit_code = cli_main(
        ["--baseline", "baseline", "--candidate", "candidate-good", "--policy", "unknown-policy"]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "error: Unsupported policy: unknown-policy" in captured.err


def test_cli_rejects_unknown_release(capsys) -> None:
    exit_code = cli_main(
        [
            "--baseline",
            "baseline",
            "--candidate",
            "missing-release",
            "--policy",
            "default",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "error: Unknown release_id: missing-release" in captured.err


def test_installed_cli_command_runs_successfully(tmp_path, monkeypatch) -> None:
    cli_name = f"evalgate{sysconfig.get_config_var('EXE') or ''}"
    cli_path = Path(sysconfig.get_path("scripts")) / cli_name

    assert cli_path.exists()

    result = subprocess.run(
        [
            str(cli_path),
            "--baseline",
            "baseline",
            "--candidate",
            "candidate-good",
            "--policy",
            "default",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )

    assert result.returncode == 0
    assert "decision: promote" in result.stdout
    assert "report:" in result.stdout


def test_save_report_rejects_invalid_report_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    try:
        store.save_report("../escape", {"decision": "promote"})
    except ValueError as exc:
        assert str(exc) == "Invalid report_id: ../escape"
    else:
        raise AssertionError("Expected invalid report_id to be rejected")
