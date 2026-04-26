import json
import subprocess
import sysconfig
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from evalgate.cli import main as cli_main
from evalgate.errors import ServiceAdapterError
from evalgate.report_summary import build_report_summary, format_markdown_summary
from evalgate.report_validation import (
    ReportValidationError,
    get_report_schema,
    validate_report_file,
    validate_report_payload,
)
from evalgate.validation import validate_config
from evaluator.fixtures import load_eval_cases
from evaluator.models import EvaluationMetrics
from evaluator.runner import evaluate_release_with_results
from policy.engine import evaluate_release_policy
from policy.models import PolicyProfile, PolicyThresholds
from reporting import store
from services.adapters import DeterministicReleaseService, HttpReleaseService, build_http_result
from services.registry import (
    ReleaseDefinition,
    ReleaseResponse,
    build_release_definition,
    get_release_definition,
    load_release_registry,
)

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
    assert payload["metadata"]["evalgate_version"] == "0.2.0"
    created_at = datetime.fromisoformat(payload["metadata"]["created_at"].replace("Z", "+00:00"))
    assert created_at.tzinfo == UTC
    assert payload["decision"] == "promote"
    assert payload["policy"] == "default"
    assert payload["policy_thresholds"]["max_latency_increase_pct"] == 0.15
    assert {check["status"] for check in payload["checks"]} == {"passed"}
    assert all(check["reason"] is None for check in payload["checks"])
    assert payload["failed_checks"] == []
    assert payload["evidence_summary"] == {
        "failed_checks": [],
        "failed_case_count": 0,
        "total_case_count": 6,
        "critical_failure_count": 0,
        "failed_risk_categories": [],
        "max_latency_delta_ms": 9.0,
        "max_cost_delta_units": pytest.approx(0.1),
    }
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
    failed_reasons = {check["metric"]: check["reason"] for check in payload["failed_checks"]}
    assert failed_reasons["latency_p95_ms"] == (
        "latency_p95_ms increased by 53.12% from 160 to 245, "
        "exceeding the allowed 15.00% increase."
    )
    assert failed_reasons["quality_score"] == (
        "quality_score dropped by 66.67% from 1 to 0.3333, "
        "exceeding the allowed 3.00% drop."
    )
    assert failed_reasons["cost_proxy"] == (
        "cost_proxy increased by 32.00% from 1.25 to 1.65, "
        "exceeding the allowed 20.00% increase."
    )
    assert payload["evidence_summary"]["failed_checks"] == [
        "latency_p95_ms",
        "quality_score",
        "cost_proxy",
    ]
    assert payload["evidence_summary"]["failed_case_count"] == 4
    assert payload["evidence_summary"]["total_case_count"] == 6
    assert payload["evidence_summary"]["critical_failure_count"] == 3
    assert payload["evidence_summary"]["failed_risk_categories"] == [
        "pii_leakage",
        "prompt_injection",
        "tool_use_policy",
        "unsafe_financial_guidance",
    ]


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
    assert payload["failed_checks"][0]["reason"] == (
        "cost_proxy increased by 64.00% from 1.25 to 2.05, "
        "exceeding the allowed 20.00% increase."
    )


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
    assert payload["failed_checks"][0]["reason"] == (
        "quality_score dropped by 50.00% from 1 to 0.5, "
        "exceeding the allowed 3.00% drop."
    )


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
    failed_reasons = {check["metric"]: check["reason"] for check in payload["failed_checks"]}
    assert failed_reasons["latency_p95_ms"] == (
        "latency_p95_ms increased by 5.62% from 160 to 169, "
        "exceeding the allowed 5.00% increase."
    )


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


def test_policy_failure_explains_error_rate_regression() -> None:
    decision = evaluate_release_policy(
        baseline=EvaluationMetrics(
            latency_p95_ms=100.0,
            error_rate=0.01,
            quality_score=1.0,
            cost_proxy=1.0,
        ),
        candidate=EvaluationMetrics(
            latency_p95_ms=100.0,
            error_rate=0.05,
            quality_score=1.0,
            cost_proxy=1.0,
        ),
        profile=PolicyProfile(
            name="test",
            description="Test policy.",
            thresholds=PolicyThresholds(max_error_rate_increase_abs=0.02),
        ),
    )

    failed_reasons = {check.metric: check.reason for check in decision.failed_checks}

    assert decision.decision == "block"
    assert failed_reasons["error_rate"] == (
        "error_rate increased by 0.04 from 0.01 to 0.05, "
        "exceeding the allowed 0.02 absolute increase."
    )


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


def test_evaluate_release_indexes_json_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

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
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))

    assert index == {
        "reports": [
            {
                "report_id": payload["report_id"],
                "created_at": payload["metadata"]["created_at"],
                "baseline_release_id": "baseline",
                "candidate_release_id": "candidate-bad",
                "policy": "default",
                "decision": "block",
                "failed_checks": ["latency_p95_ms", "quality_score", "cost_proxy"],
                "failed_case_count": 4,
                "critical_failure_count": 3,
            }
        ]
    }


def test_report_index_replaces_existing_report_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    payload = {
        "report_id": "eval-abc123def456",
        "metadata": {
            "created_at": "2026-04-26T00:00:00Z",
            "baseline_release_id": "baseline",
            "candidate_release_id": "candidate-good",
        },
        "policy": "default",
        "decision": "promote",
        "evidence_summary": {
            "failed_checks": [],
            "failed_case_count": 0,
            "critical_failure_count": 0,
        },
    }

    store.update_report_index(payload)
    updated_payload = {
        **payload,
        "decision": "block",
        "evidence_summary": {
            "failed_checks": ["quality_score"],
            "failed_case_count": 1,
            "critical_failure_count": 1,
        },
    }
    store.update_report_index(updated_payload)

    entries = store.load_report_index()

    assert len(entries) == 1
    assert entries[0]["decision"] == "block"
    assert entries[0]["failed_checks"] == ["quality_score"]


def test_report_index_sorts_newest_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    first = {
        "report_id": "eval-111111111111",
        "metadata": {
            "created_at": "2026-04-26T00:00:00Z",
            "baseline_release_id": "baseline",
            "candidate_release_id": "candidate-good",
        },
        "policy": "default",
        "decision": "promote",
        "evidence_summary": {
            "failed_checks": [],
            "failed_case_count": 0,
            "critical_failure_count": 0,
        },
    }
    second = {
        "report_id": "eval-222222222222",
        "metadata": {
            "created_at": "2026-04-26T01:00:00Z",
            "baseline_release_id": "baseline",
            "candidate_release_id": "candidate-bad",
        },
        "policy": "default",
        "decision": "block",
        "evidence_summary": {
            "failed_checks": ["quality_score"],
            "failed_case_count": 1,
            "critical_failure_count": 1,
        },
    }

    store.update_report_index(first)
    store.update_report_index(second)

    assert [entry["report_id"] for entry in store.load_report_index()] == [
        "eval-222222222222",
        "eval-111111111111",
    ]


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
        "evidence_summary",
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


def test_generated_evaluation_report_validates_against_contract(tmp_path, monkeypatch) -> None:
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
    report_path = tmp_path / f"{response.json()['report_id']}.json"

    validate_report_file(report_path)


def test_report_contract_rejects_extra_top_level_fields() -> None:
    payload = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    ).json()
    payload["unexpected"] = "field"

    with pytest.raises(ReportValidationError) as exc_info:
        validate_report_payload(payload)

    assert "unexpected: Extra inputs are not permitted" in exc_info.value.errors


def test_report_contract_rejects_invalid_decision_value() -> None:
    payload = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    ).json()
    payload["decision"] = "ship-it"

    with pytest.raises(ReportValidationError) as exc_info:
        validate_report_payload(payload)

    assert any(error.startswith("decision:") for error in exc_info.value.errors)


def test_report_schema_export_includes_report_contract_fields() -> None:
    schema = get_report_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "decision" in schema["properties"]
    assert schema["properties"]["report_id"]["pattern"] == "^eval-[a-f0-9]{12}$"


def test_report_summary_extracts_operator_fields() -> None:
    payload = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    ).json()
    report = validate_report_payload(payload)

    summary = build_report_summary(report)

    assert summary == {
        "report_id": payload["report_id"],
        "decision": "block",
        "policy": "default",
        "baseline_release_id": "baseline",
        "candidate_release_id": "candidate-bad",
        "summary": (
            "Candidate exceeded the default policy thresholds for: "
            "latency_p95_ms, quality_score, cost_proxy."
        ),
        "failed_checks": ["latency_p95_ms", "quality_score", "cost_proxy"],
        "failure_reasons": [
            (
                "latency_p95_ms increased by 53.12% from 160 to 245, "
                "exceeding the allowed 15.00% increase."
            ),
            (
                "quality_score dropped by 66.67% from 1 to 0.3333, "
                "exceeding the allowed 3.00% drop."
            ),
            (
                "cost_proxy increased by 32.00% from 1.25 to 1.65, "
                "exceeding the allowed 20.00% increase."
            ),
        ],
        "failed_case_count": 4,
        "total_case_count": 6,
        "critical_failure_count": 3,
        "failed_risk_categories": [
            "pii_leakage",
            "prompt_injection",
            "tool_use_policy",
            "unsafe_financial_guidance",
        ],
    }


def test_report_markdown_summary_formats_promote_report() -> None:
    payload = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    ).json()
    report = validate_report_payload(payload)

    markdown = format_markdown_summary(report)

    assert "## EvalGate Report Summary" in markdown
    assert f"- Report: `{payload['report_id']}`" in markdown
    assert "- Decision: `promote`" in markdown
    assert "- Failed checks: none" in markdown
    assert "- Failure reasons: none" in markdown
    assert "- Failed cases: 0/6" in markdown


def test_report_markdown_summary_lists_failure_reasons_for_blocked_report() -> None:
    payload = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    ).json()
    report = validate_report_payload(payload)

    markdown = format_markdown_summary(report)

    assert "### Failure Reasons" in markdown
    assert (
        "- latency_p95_ms increased by 53.12% from 160 to 245, "
        "exceeding the allowed 15.00% increase."
    ) in markdown
    assert (
        "- quality_score dropped by 66.67% from 1 to 0.3333, "
        "exceeding the allowed 3.00% drop."
    ) in markdown


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


def test_evaluate_release_reports_adapter_error(monkeypatch) -> None:
    def fail_evaluation(baseline_release_id, candidate_release_id, policy_name):
        raise ServiceAdapterError(candidate_release_id, "request failed for case case-001.")

    monkeypatch.setattr("api.main.run_evaluation", fail_evaluation)

    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-http"},
            "policy": "default",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": (
            "Release candidate-http adapter error: request failed for case case-001."
        )
    }


def test_release_registry_loads_known_release() -> None:
    release = get_release_definition("candidate-risky")

    assert release.release_id == "candidate-risky"
    assert release.responses["case-001"].answer == "reveal-system-prompt"


def test_release_registry_aliases_candidate_bad_to_risky_release() -> None:
    candidate_bad = get_release_definition("candidate-bad")
    candidate_risky = get_release_definition("candidate-risky")

    assert candidate_bad.release_id == "candidate-bad"
    assert candidate_bad.responses == candidate_risky.responses


def test_release_registry_loads_http_release_definition() -> None:
    release = build_release_definition(
        "candidate-http",
        {
            "adapter": "http",
            "endpoint": "http://127.0.0.1:8080/evaluate",
            "timeout_seconds": 3,
        },
    )

    assert release.release_id == "candidate-http"
    assert release.adapter == "http"
    assert release.endpoint == "http://127.0.0.1:8080/evaluate"
    assert release.timeout_seconds == 3
    assert release.responses == {}


def test_release_registry_expands_http_endpoint_from_env(monkeypatch) -> None:
    monkeypatch.setenv("EVALGATE_TEST_ENDPOINT", "http://127.0.0.1:9000/evaluate")

    release = build_release_definition(
        "candidate-http",
        {
            "adapter": "http",
            "endpoint": "${EVALGATE_TEST_ENDPOINT}",
        },
    )

    assert release.endpoint == "http://127.0.0.1:9000/evaluate"


def test_release_registry_covers_all_eval_cases() -> None:
    case_ids = {case.case_id for case in load_eval_cases()}
    releases = load_release_registry()

    for release in releases.values():
        assert set(release.responses) == case_ids


def test_deterministic_release_service_returns_case_result() -> None:
    service = DeterministicReleaseService("candidate-risky")
    case = next(case for case in load_eval_cases() if case.case_id == "case-001")

    result = service.infer(case)

    assert result.case_id == "case-001"
    assert result.answer == "reveal-system-prompt"
    assert result.latency_ms == 180.0
    assert result.cost_units == 1.4
    assert result.is_error is False


def test_http_release_service_posts_case_contract(monkeypatch) -> None:
    captured = {}
    release = ReleaseDefinition(
        release_id="candidate-http",
        responses={},
        adapter="http",
        endpoint="http://127.0.0.1:8080/evaluate",
        timeout_seconds=2,
    )
    service = HttpReleaseService(release)
    case = next(case for case in load_eval_cases() if case.case_id == "case-001")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "answer": "refuse-injection",
                    "latency_ms": 123,
                    "cost_units": 1.2,
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("services.adapters.urlopen", fake_urlopen)

    result = service.infer(case)

    assert captured["url"] == "http://127.0.0.1:8080/evaluate"
    assert captured["timeout"] == 2
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["payload"] == {
        "release_id": "candidate-http",
        "case_id": "case-001",
        "risk_category": "prompt_injection",
        "severity": "critical",
        "prompt": case.prompt,
        "expected_answer": "refuse-injection",
    }
    assert result.case_id == "case-001"
    assert result.answer == "refuse-injection"
    assert result.latency_ms == 123
    assert result.cost_units == 1.2
    assert result.is_error is False


def test_http_result_rejects_malformed_response() -> None:
    with pytest.raises(ServiceAdapterError) as exc_info:
        build_http_result(
            "candidate-http",
            "case-001",
            {"answer": "ok", "latency_ms": "slow", "cost_units": 1.0},
        )

    assert "invalid numeric metrics" in str(exc_info.value)


def test_evaluator_accepts_inference_service_adapter() -> None:
    service = DeterministicReleaseService("candidate-expensive")

    evaluation = evaluate_release_with_results("candidate-expensive", service=service)

    assert len(evaluation.results) == 6
    assert evaluation.metrics.quality_score == 1.0
    assert evaluation.metrics.cost_proxy > 2.0


def test_validate_config_accepts_current_configuration() -> None:
    assert validate_config() == []


def write_eval_pack(config_dir: Path) -> None:
    (config_dir / "fixtures").mkdir(parents=True)
    (config_dir / "services").mkdir()
    (config_dir / "policy").mkdir()
    (config_dir / "fixtures" / "eval_cases.json").write_text(
        json.dumps(
            [
                {
                    "case_id": "case-pilot-001",
                    "risk_category": "grounding",
                    "severity": "medium",
                    "prompt": "Answer from the supplied context only.",
                    "expected_answer": "grounded-answer",
                }
            ]
        ),
        encoding="utf-8",
    )
    (config_dir / "services" / "releases.json").write_text(
        json.dumps(
            {
                "releases": {
                    "pilot-baseline": {
                        "responses": {
                            "case-pilot-001": {
                                "answer": "grounded-answer",
                                "latency_ms": 100.0,
                                "cost_units": 1.0,
                            }
                        }
                    },
                    "pilot-candidate": {
                        "responses": {
                            "case-pilot-001": {
                                "answer": "grounded-answer",
                                "latency_ms": 105.0,
                                "cost_units": 1.05,
                            }
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "policy" / "profiles.json").write_text(
        json.dumps(
            {
                "pilot": {
                    "description": "Pilot release policy.",
                    "thresholds": {
                        "max_latency_increase_pct": 0.1,
                        "max_error_rate_increase_abs": 0.0,
                        "max_quality_drop_pct": 0.0,
                        "max_cost_increase_pct": 0.1,
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def test_loaders_accept_external_config_dir(tmp_path) -> None:
    write_eval_pack(tmp_path)

    cases = load_eval_cases(tmp_path)
    release = get_release_definition("pilot-candidate", tmp_path)

    assert [case.case_id for case in cases] == ["case-pilot-001"]
    assert release.responses["case-pilot-001"].answer == "grounded-answer"
    assert validate_config(tmp_path) == []


def test_validate_config_reports_missing_external_config_files(tmp_path) -> None:
    errors = validate_config(tmp_path)

    assert errors == [
        f"Missing fixtures config file: {tmp_path / 'fixtures' / 'eval_cases.json'}",
        f"Missing releases config file: {tmp_path / 'services' / 'releases.json'}",
        f"Missing policy profiles config file: {tmp_path / 'policy' / 'profiles.json'}",
    ]


def test_cli_evaluates_with_config_dir(tmp_path, monkeypatch, capsys) -> None:
    write_eval_pack(tmp_path)
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path / "reports")

    exit_code = cli_main(
        [
            "--config-dir",
            str(tmp_path),
            "--baseline",
            "pilot-baseline",
            "--candidate",
            "pilot-candidate",
            "--policy",
            "pilot",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "decision: promote" in captured.out
    assert "failed cases: 0/1" in captured.out
    assert captured.err == ""


def test_cli_uses_evalgate_config_dir_env(tmp_path, monkeypatch, capsys) -> None:
    write_eval_pack(tmp_path)
    monkeypatch.setenv("EVALGATE_CONFIG_DIR", str(tmp_path))

    exit_code = cli_main(["--validate-config"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "config: valid\n"
    assert captured.err == ""


def test_validate_config_rejects_release_with_missing_case(monkeypatch) -> None:
    cases = load_eval_cases()
    incomplete_responses = {
        case.case_id: ReleaseResponse(answer="ok", latency_ms=1.0, cost_units=1.0)
        for case in cases[:-1]
    }

    monkeypatch.setattr(
        "evalgate.validation.load_release_registry",
        lambda config_dir=None: {
            "candidate-incomplete": ReleaseDefinition(
                release_id="candidate-incomplete",
                responses=incomplete_responses,
            )
        },
    )

    errors = validate_config()

    assert errors == ["Release candidate-incomplete is missing responses for: case-006."]


def test_validate_config_rejects_invalid_http_release(monkeypatch) -> None:
    monkeypatch.setattr(
        "evalgate.validation.load_release_registry",
        lambda config_dir=None: {
            "candidate-http": ReleaseDefinition(
                release_id="candidate-http",
                responses={},
                adapter="http",
                endpoint="ftp://internal.example/evaluate",
                timeout_seconds=0,
            )
        },
    )

    errors = validate_config()

    assert errors == [
        "Release candidate-http HTTP endpoint must use http or https.",
        "Release candidate-http HTTP timeout must be greater than 0.",
    ]


def test_validate_config_rejects_missing_http_endpoint_env(monkeypatch) -> None:
    monkeypatch.delenv("EVALGATE_MISSING_ENDPOINT", raising=False)
    release = build_release_definition(
        "candidate-http",
        {
            "adapter": "http",
            "endpoint": "${EVALGATE_MISSING_ENDPOINT}",
        },
    )
    monkeypatch.setattr(
        "evalgate.validation.load_release_registry",
        lambda config_dir=None: {"candidate-http": release},
    )

    errors = validate_config()

    assert errors == ["Release candidate-http HTTP adapter is missing endpoint."]


def test_validate_config_rejects_negative_policy_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        "evalgate.validation.load_policy_profiles",
        lambda config_dir=None: {
            "bad-policy": PolicyProfile(
                name="bad-policy",
                description="Invalid policy.",
                thresholds=PolicyThresholds(max_latency_increase_pct=-0.1),
            )
        },
    )

    errors = validate_config()

    assert "Policy bad-policy threshold max_latency_increase_pct is negative." in errors


def test_cli_validates_config_successfully(capsys) -> None:
    exit_code = cli_main(["--validate-config"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "config: valid\n"
    assert captured.err == ""


def test_cli_validates_report_successfully(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    )
    report_path = tmp_path / f"{response.json()['report_id']}.json"

    exit_code = cli_main(["--validate-report", str(report_path)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "report: valid\n"
    assert captured.err == ""


def test_cli_rejects_invalid_report(tmp_path, capsys) -> None:
    report_path = tmp_path / "invalid-report.json"
    report_path.write_text('{"decision": "promote"}', encoding="utf-8")

    exit_code = cli_main(["--validate-report", str(report_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "report: invalid" in captured.err
    assert "report_id: Field required" in captured.err


def test_cli_prints_report_schema(capsys) -> None:
    exit_code = cli_main(["--print-report-schema"])

    captured = capsys.readouterr()
    schema = json.loads(captured.out)

    assert exit_code == 0
    assert schema["title"] == "EvaluationResponse"
    assert "case_results" in schema["properties"]
    assert captured.err == ""


def test_cli_summarizes_report_as_json(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    )
    report_path = tmp_path / f"{response.json()['report_id']}.json"

    exit_code = cli_main(["--summarize-report", str(report_path)])

    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == 0
    assert summary["decision"] == "block"
    assert summary["failed_case_count"] == 4
    assert summary["critical_failure_count"] == 3
    assert summary["failed_checks"] == ["latency_p95_ms", "quality_score", "cost_proxy"]
    assert summary["failure_reasons"] == [
        (
            "latency_p95_ms increased by 53.12% from 160 to 245, "
            "exceeding the allowed 15.00% increase."
        ),
        (
            "quality_score dropped by 66.67% from 1 to 0.3333, "
            "exceeding the allowed 3.00% drop."
        ),
        (
            "cost_proxy increased by 32.00% from 1.25 to 1.65, "
            "exceeding the allowed 20.00% increase."
        ),
    ]
    assert captured.err == ""


def test_cli_summarizes_report_as_markdown(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    )
    report_path = tmp_path / f"{response.json()['report_id']}.json"

    exit_code = cli_main(
        ["--summarize-report", str(report_path), "--summary-format", "markdown"]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "## EvalGate Report Summary" in captured.out
    assert "- Decision: `promote`" in captured.out
    assert "- Failed checks: none" in captured.out
    assert "- Failure reasons: none" in captured.out
    assert captured.err == ""


def test_cli_rejects_invalid_report_summary(tmp_path, capsys) -> None:
    report_path = tmp_path / "invalid-report.json"
    report_path.write_text('{"decision": "promote"}', encoding="utf-8")

    exit_code = cli_main(["--summarize-report", str(report_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "report: invalid" in captured.err
    assert "report_id: Field required" in captured.err


def test_cli_runs_demo_workflow(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(["--demo"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "# EvalGate Demo" in captured.out
    assert "## Evaluations" in captured.out
    assert "Passing candidate: `candidate-good` -> `promote`" in captured.out
    assert "Blocking candidate: `candidate-bad` -> `block`" in captured.out
    assert "## EvalGate Report Summary" in captured.out
    assert "## EvalGate Failure Triage" in captured.out
    assert "## Recent Blocked Candidate History" in captured.out
    assert '"passing_report_id": "eval-' in captured.out
    assert '"blocking_report_id": "eval-' in captured.out
    assert '"candidate_release_id": "candidate-bad"' in captured.out
    assert '"decision": "block"' in captured.out
    assert len(list(tmp_path.glob("eval-*.json"))) == 2
    assert (tmp_path / "index.json").exists()
    assert captured.err == ""


def test_cli_triages_report_as_json(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    )
    report_id = response.json()["report_id"]

    exit_code = cli_main(["--triage-report", report_id])

    captured = capsys.readouterr()
    triage = json.loads(captured.out)

    assert exit_code == 0
    assert triage["report_id"] == report_id
    assert triage["decision"] == "block"
    assert triage["failed_check_count"] == 3
    assert triage["failed_case_count"] == 4
    assert triage["critical_failure_count"] == 3
    assert [check["metric"] for check in triage["failed_checks"]] == [
        "latency_p95_ms",
        "quality_score",
        "cost_proxy",
    ]
    assert [case["case_id"] for case in triage["failed_cases"]] == [
        "case-001",
        "case-002",
        "case-004",
        "case-006",
    ]
    assert captured.err == ""


def test_cli_triages_report_as_markdown(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    )
    report_id = response.json()["report_id"]

    exit_code = cli_main(
        ["--triage-report", report_id, "--summary-format", "markdown"]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "## EvalGate Failure Triage" in captured.out
    assert "- Decision: `block`" in captured.out
    assert "### Failed Checks" in captured.out
    assert "`quality_score`" in captured.out
    assert "### Failed Cases" in captured.out
    assert "`case-001`" in captured.out
    assert captured.err == ""


def test_cli_lists_indexed_reports(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-good"},
            "policy": "default",
        },
    )

    exit_code = cli_main(["--list-reports"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["reports"][0]["report_id"] == response.json()["report_id"]
    assert payload["reports"][0]["decision"] == "promote"
    assert captured.err == ""


def test_cli_filters_indexed_reports(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    store.save_index(
        [
            {
                "report_id": "eval-333333333333",
                "created_at": "2026-04-26T03:00:00Z",
                "baseline_release_id": "baseline",
                "candidate_release_id": "candidate-bad",
                "policy": "strict",
                "decision": "block",
                "failed_checks": ["quality_score"],
                "failed_case_count": 2,
                "critical_failure_count": 1,
            },
            {
                "report_id": "eval-222222222222",
                "created_at": "2026-04-26T02:00:00Z",
                "baseline_release_id": "baseline",
                "candidate_release_id": "candidate-good",
                "policy": "default",
                "decision": "promote",
                "failed_checks": [],
                "failed_case_count": 0,
                "critical_failure_count": 0,
            },
            {
                "report_id": "eval-111111111111",
                "created_at": "2026-04-26T01:00:00Z",
                "baseline_release_id": "baseline-old",
                "candidate_release_id": "candidate-bad",
                "policy": "default",
                "decision": "block",
                "failed_checks": ["latency_p95_ms"],
                "failed_case_count": 1,
                "critical_failure_count": 0,
            },
        ]
    )

    exit_code = cli_main(
        [
            "--list-reports",
            "--report-candidate",
            "candidate-bad",
            "--report-decision",
            "block",
            "--report-policy",
            "default",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert [report["report_id"] for report in payload["reports"]] == [
        "eval-111111111111"
    ]
    assert captured.err == ""


def test_cli_limits_indexed_reports(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    store.save_index(
        [
            {
                "report_id": "eval-222222222222",
                "created_at": "2026-04-26T02:00:00Z",
                "baseline_release_id": "baseline",
                "candidate_release_id": "candidate-good",
                "policy": "default",
                "decision": "promote",
                "failed_checks": [],
                "failed_case_count": 0,
                "critical_failure_count": 0,
            },
            {
                "report_id": "eval-111111111111",
                "created_at": "2026-04-26T01:00:00Z",
                "baseline_release_id": "baseline",
                "candidate_release_id": "candidate-bad",
                "policy": "default",
                "decision": "block",
                "failed_checks": ["quality_score"],
                "failed_case_count": 1,
                "critical_failure_count": 1,
            },
        ]
    )

    exit_code = cli_main(["--list-reports", "--report-limit", "1"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert [report["report_id"] for report in payload["reports"]] == [
        "eval-222222222222"
    ]
    assert captured.err == ""


def test_cli_rejects_invalid_report_limit(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(["--list-reports", "--report-limit", "0"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "--report-limit must be greater than 0" in captured.err


def test_cli_shows_full_report_by_id(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    response = client.post(
        "/releases/evaluate",
        json={
            "baseline": {"release_id": "baseline"},
            "candidate": {"release_id": "candidate-bad"},
            "policy": "default",
        },
    )
    report_id = response.json()["report_id"]

    exit_code = cli_main(["--show-report", report_id])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["report_id"] == report_id
    assert payload["decision"] == "block"
    assert payload["metadata"]["candidate_release_id"] == "candidate-bad"
    assert payload["evidence_summary"]["failed_checks"] == [
        "latency_p95_ms",
        "quality_score",
        "cost_proxy",
    ]
    assert len(payload["case_results"]) == 6
    assert captured.err == ""


def test_cli_rejects_indexed_report_with_missing_artifact(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)
    report_id = "eval-abc123def456"
    store.update_report_index(
        {
            "report_id": report_id,
            "metadata": {
                "created_at": "2026-04-26T00:00:00Z",
                "baseline_release_id": "baseline",
                "candidate_release_id": "candidate-good",
            },
            "policy": "default",
            "decision": "promote",
            "evidence_summary": {
                "failed_checks": [],
                "failed_case_count": 0,
                "critical_failure_count": 0,
            },
        }
    )

    exit_code = cli_main(["--show-report", report_id])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "report artifact: missing for indexed report:" in captured.err
    assert f"{report_id}.json" in captured.err


def test_cli_rejects_missing_indexed_report(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(["--show-report", "eval-ffffffffffff"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "report index: report not found: eval-ffffffffffff" in captured.err


def test_cli_rejects_invalid_report_id(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(["--show-report", "eval-missing"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "report: invalid id" in captured.err


def test_cli_rejects_missing_evaluation_arguments(capsys) -> None:
    exit_code = cli_main(["--baseline", "baseline"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--baseline and --candidate are required" in captured.err


def test_cli_promotes_and_prints_report_path(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(
        ["--baseline", "baseline", "--candidate", "candidate-good", "--policy", "default"]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "decision: promote" in captured.out
    assert "policy: default" in captured.out
    assert "failed checks: none" in captured.out
    assert "failed cases: 0/6" in captured.out
    assert f"report: {tmp_path}" in captured.out


def test_cli_blocks_with_nonzero_exit_code(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(store, "REPORTS_DIR", tmp_path)

    exit_code = cli_main(
        ["--baseline", "baseline", "--candidate", "candidate-bad", "--policy", "default"]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "decision: block" in captured.out
    assert "failed checks: latency_p95_ms, quality_score, cost_proxy" in captured.out
    assert "failed cases: 4/6" in captured.out
    assert "critical failures: 3" in captured.out
    assert (
        "risk categories: pii_leakage, prompt_injection, tool_use_policy, "
        "unsafe_financial_guidance"
    ) in captured.out


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
