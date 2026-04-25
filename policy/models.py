from dataclasses import dataclass


@dataclass(slots=True)
class PolicyThresholds:
    max_latency_increase_pct: float = 0.15
    max_error_rate_increase_abs: float = 0.02
    max_quality_drop_pct: float = 0.03
    max_cost_increase_pct: float = 0.20


@dataclass(slots=True)
class PolicyProfile:
    name: str
    description: str
    thresholds: PolicyThresholds
