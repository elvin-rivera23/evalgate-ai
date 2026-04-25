from pydantic import BaseModel, ConfigDict


class ReleaseTarget(BaseModel):
    release_id: str


class EvaluationRequest(BaseModel):
    baseline: ReleaseTarget
    candidate: ReleaseTarget
    policy: str = "default"


class HealthResponse(BaseModel):
    status: str


class EvaluationMetadata(BaseModel):
    created_at: str
    baseline_release_id: str
    candidate_release_id: str
    policy: str
    evalgate_version: str


class FailedCheck(BaseModel):
    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: str = "failed"


class PolicyCheck(BaseModel):
    metric: str
    baseline: float
    candidate: float
    threshold_type: str
    threshold_value: float
    delta: float
    status: str


class CaseResult(BaseModel):
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


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    metadata: EvaluationMetadata
    policy: str
    policy_thresholds: dict[str, float]
    decision: str
    summary: str
    checks: list[PolicyCheck]
    failed_checks: list[FailedCheck]
    case_results: list[CaseResult]
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    deltas: dict[str, float]
