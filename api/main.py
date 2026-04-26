from fastapi import FastAPI, HTTPException

from api.schemas import EvaluationRequest, EvaluationResponse, HealthResponse
from evalgate.errors import ServiceAdapterError, UnknownReleaseError, UnsupportedPolicyError
from evalgate.orchestration import run_evaluation

app = FastAPI(title="EvalGate AI", version="0.2.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/releases/evaluate", response_model=EvaluationResponse)
def evaluate_release_pair(request: EvaluationRequest) -> EvaluationResponse:
    try:
        evaluation = run_evaluation(
            baseline_release_id=request.baseline.release_id,
            candidate_release_id=request.candidate.release_id,
            policy_name=request.policy,
        )
    except UnsupportedPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnknownReleaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceAdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return evaluation.response
