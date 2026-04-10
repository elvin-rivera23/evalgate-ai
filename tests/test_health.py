import json
import subprocess
import sysconfig
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

    assert payload["decision"] == "promote"
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
    assert "latency_p95_ms" in failed_metrics
    assert "quality_score" in failed_metrics
    assert "cost_proxy" in failed_metrics


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


def test_evaluate_release_rejects_unsupported_policy() -> None:
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "strict",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported policy: strict"}


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
        ["--baseline", "baseline", "--candidate", "candidate-good", "--policy", "strict"]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "error: Unsupported policy: strict" in captured.err


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
    cli_path = Path(sysconfig.get_path("scripts")) / "evalgate"

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
