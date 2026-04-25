import json
import subprocess
import sysconfig
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from evalgate.cli import main as cli_main
from reporting import store

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
    assert payload["baseline_metrics"]["quality_score"] == 1.0
    assert payload["candidate_metrics"]["quality_score"] == 1.0


def test_evaluate_release_blocks_candidate_with_regressions() -> None:
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

    failed_metrics = {check["metric"] for check in payload["failed_checks"]}
    assert payload["decision"] == "block"
    assert payload["policy"] == "default"
    assert len(payload["checks"]) == 4
    assert "latency_p95_ms" in failed_metrics
    assert "quality_score" in failed_metrics
    assert "cost_proxy" in failed_metrics


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
