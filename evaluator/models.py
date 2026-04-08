from dataclasses import dataclass


@dataclass(slots=True)
class EvaluationMetrics:
    latency_p95_ms: float
    error_rate: float
    quality_score: float
    cost_proxy: float
