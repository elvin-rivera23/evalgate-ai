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
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    deltas: dict[str, float]
