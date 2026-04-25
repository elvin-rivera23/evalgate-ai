from dataclasses import dataclass


@dataclass(slots=True)
class EvaluationMetrics:
    latency_p95_ms: float
    error_rate: float
    quality_score: float
    cost_proxy: float


@dataclass(slots=True)
class ServiceRunResult:
    case_id: str
    latency_ms: float
    cost_units: float
    answer: str
    is_error: bool


@dataclass(slots=True)
class ReleaseEvaluation:
    metrics: EvaluationMetrics
    results: list[ServiceRunResult]
