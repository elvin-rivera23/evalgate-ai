from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReleaseTarget(BaseModel):
    release_id: str


class EvaluationRequest(BaseModel):
    baseline: ReleaseTarget
    candidate: ReleaseTarget
    policy: str = "default"


class HealthResponse(BaseModel):
    status: str


class EvaluationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: str
    baseline_release_id: str
    candidate_release_id: str
    policy: str
    evalgate_version: str


class FailedCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: Literal["failed"]


class PolicyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: Literal["passed", "failed"]


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    risk_category: str
    severity: str
    expected_answer: str
    baseline_answer: str
    candidate_answer: str
    passed: bool
    baseline_latency_ms: float
    candidate_latency_ms: float
    latency_delta_ms: float
    baseline_cost_units: float
    candidate_cost_units: float
    cost_delta_units: float


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failed_checks: list[str]
    failed_case_count: int
    total_case_count: int
    critical_failure_count: int
    failed_risk_categories: list[str]
    max_latency_delta_ms: float
    max_cost_delta_units: float


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(pattern=r"^eval-[a-f0-9]{12}$")
    metadata: EvaluationMetadata
    policy: str
    policy_thresholds: dict[str, float]
    decision: Literal["promote", "block"]
    summary: str
    checks: list[PolicyCheck]
    failed_checks: list[FailedCheck]
    evidence_summary: EvidenceSummary
    case_results: list[CaseResult]
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    deltas: dict[str, float]
