from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from evalgate.errors import UnknownReleaseError
from evaluator.fixtures import EvalCase
from services.adapters import get_inference_service


class InferenceRequest(BaseModel):
    case_id: str
    prompt: str


def create_service_app(release_id: str) -> FastAPI:
    service = get_inference_service(release_id)
    app = FastAPI(title=f"EvalGate service: {release_id}")

    @app.post("/infer")
    def infer(request: InferenceRequest) -> dict[str, float | str]:
        try:
            result = service.infer(
                EvalCase(
                    case_id=request.case_id,
                    risk_category="unknown",
                    severity="unknown",
                    prompt=request.prompt,
                    expected_answer="unknown",
                )
            )
        except UnknownReleaseError:
            raise HTTPException(status_code=404, detail="Unknown fixture case.")
        return {
            "answer": result.answer,
            "latency_ms": result.latency_ms,
            "cost_units": result.cost_units,
        }

    return app


def get_service_app(release_id: str) -> FastAPI:
    try:
        get_inference_service(release_id)
    except UnknownReleaseError:
        raise UnknownReleaseError(release_id)
    return create_service_app(release_id)
