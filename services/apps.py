from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class InferenceRequest(BaseModel):
    case_id: str
    prompt: str


SERVICE_RESPONSES = {
    "baseline": {
        "case-001": {"answer": "allow", "latency_ms": 120.0, "cost_units": 1.0},
        "case-002": {"answer": "review", "latency_ms": 135.0, "cost_units": 1.1},
        "case-003": {"answer": "block", "latency_ms": 150.0, "cost_units": 1.2},
    },
    "candidate-good": {
        "case-001": {"answer": "allow", "latency_ms": 126.0, "cost_units": 1.1},
        "case-002": {"answer": "review", "latency_ms": 142.0, "cost_units": 1.2},
        "case-003": {"answer": "block", "latency_ms": 158.0, "cost_units": 1.3},
    },
    "candidate-bad": {
        "case-001": {"answer": "allow", "latency_ms": 175.0, "cost_units": 1.4},
        "case-002": {"answer": "allow", "latency_ms": 205.0, "cost_units": 1.5},
        "case-003": {"answer": "block", "latency_ms": 230.0, "cost_units": 1.6},
    },
}


def create_service_app(release_id: str) -> FastAPI:
    app = FastAPI(title=f"EvalGate service: {release_id}")

    @app.post("/infer")
    def infer(request: InferenceRequest) -> dict[str, float | str]:
        case_outputs = SERVICE_RESPONSES[release_id]
        payload = case_outputs.get(request.case_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Unknown fixture case.")
        return payload

    return app


def get_service_app(release_id: str) -> FastAPI:
    if release_id not in SERVICE_RESPONSES:
        raise ValueError(f"Unknown release_id: {release_id}")
    return create_service_app(release_id)
