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

- FastAPI app plus `POST /releases/evaluate`
- deterministic sample baseline and candidate services
- fixture-driven evaluator and threshold policy logic
- test harness
- lightweight CI and security checks

The higher-level product writeup lives in [docs/overview.md](docs/overview.md).

## Current Capabilities

- sample baseline and candidate services
- deterministic fixture-driven evaluator
- config-backed policy profiles for different release risk tolerances
- comparison and threshold policy engine
- persisted JSON reports with policy checks and metric deltas
- FastAPI endpoint for service integration
- CLI entrypoint for local runs and CI
- passing and blocked demo release paths

## Development

Install dependencies:

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the API locally:

```bash
uvicorn api.main:app --reload
```

Run a sample evaluation:

```bash
curl -X POST http://127.0.0.1:8000/releases/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "baseline": {"release_id": "baseline"},
    "candidate": {"release_id": "candidate-bad"},
    "policy": "default"
  }'
```

Run tests:

```bash
pytest
```

Run a local CLI evaluation:

```bash
evalgate --baseline baseline --candidate candidate-good --policy default
```

The CLI exits with `0` for `promote`, `1` for `block`, and `2` for invalid input such as an unsupported policy.

## Policy Profiles

EvalGate ships with config-backed policy profiles in `policy/profiles.json`:

- `default`: balanced release gate for general model-backed services
- `strict`: tighter thresholds for high-risk services
- `cost-sensitive`: stricter cost guardrail for high-volume services
- `quality-critical`: zero-tolerance quality regression gate

Each evaluation report includes the active policy name, the threshold snapshot used for the run, all pass/fail policy checks, failed checks, baseline metrics, candidate metrics, and deltas.

## CI And Security

The repository currently uses a lightweight GitHub Actions setup:

- `ruff` linting
- `pytest`
- `gitleaks` secret scanning
- dependency review on pull requests
- CodeQL scanning on pull requests to `main`, pushes to `main`, and a weekly schedule

You can also run a local secret scan before pushing:

```bash
gitleaks git .
```

Repository-level GitHub features such as secret scanning and Dependabot alerts should also be enabled in repo settings.

## Reports

Each evaluation run now persists a machine-readable JSON report to `reports/<report_id>.json`.

That artifact is intended to be the audit trail for CI and operator workflows.
