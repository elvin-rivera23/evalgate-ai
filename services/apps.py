from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from evalgate.errors import UnknownReleaseError
from services.registry import get_release_definition


class InferenceRequest(BaseModel):
    case_id: str
    prompt: str


def create_service_app(release_id: str) -> FastAPI:
    release = get_release_definition(release_id)
    app = FastAPI(title=f"EvalGate service: {release_id}")

    @app.post("/infer")
    def infer(request: InferenceRequest) -> dict[str, float | str]:
        payload = release.responses.get(request.case_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Unknown fixture case.")
        return {
            "answer": payload.answer,
            "latency_ms": payload.latency_ms,
            "cost_units": payload.cost_units,
        }

    return app


def get_service_app(release_id: str) -> FastAPI:
    try:
        get_release_definition(release_id)
    except UnknownReleaseError:
        raise UnknownReleaseError(release_id)
    return create_service_app(release_id)
