# EvalGate AI

EvalGate AI is a policy-driven release gate for model-backed services. It evaluates a candidate release against a baseline, applies explicit policy thresholds, and returns a final decision of `promote` or `block` with a machine-readable audit trail.

The repository is being built as internal platform tooling for release engineering and MLOps teams.

## Goals

- compare baseline and candidate releases against the same fixture set
- detect regressions in latency, reliability, quality, and cost proxy
- apply explicit release policies instead of ad hoc judgment
- generate decision reports that CI and operators can consume

## Current Status

Initial scaffold is in place:

- FastAPI app skeleton
- domain packages for evaluation and policy logic
- test harness
- lightweight CI

The higher-level product writeup lives in [docs/overview.md](docs/overview.md).

## Planned MVP

- sample baseline and candidate services
- deterministic evaluator
- comparison and policy engine
- persisted JSON reports
- CLI entrypoint for local runs and CI
- one passing and one blocked demo release

## Development

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the API locally:

```bash
uvicorn api.main:app --reload
```

Run tests:

```bash
pytest
```
