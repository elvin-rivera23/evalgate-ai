from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from api.schemas import EvaluationRequest, EvaluationResponse, HealthResponse
from evaluator.runner import evaluate_release
from policy.engine import evaluate_release_policy
from reporting.store import save_report

app = FastAPI(title="EvalGate AI", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/releases/evaluate", response_model=EvaluationResponse)
def evaluate_release_pair(request: EvaluationRequest) -> EvaluationResponse:
    try:
        baseline_metrics = evaluate_release(request.baseline.release_id)
        candidate_metrics = evaluate_release(request.candidate.release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    decision = evaluate_release_policy(
        baseline=baseline_metrics,
        candidate=candidate_metrics,
    )

    response = EvaluationResponse(
        report_id=decision.report_id,
        decision=decision.decision,
        summary=decision.summary,
        failed_checks=[asdict(check) for check in decision.failed_checks],
        baseline_metrics=decision.baseline_metrics,
        candidate_metrics=decision.candidate_metrics,
        deltas=decision.deltas,
    )

    save_report(response.report_id, response.model_dump())
    return response
