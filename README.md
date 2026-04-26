# EvalGate AI

EvalGate AI is a policy-driven release gate for model-backed services. It evaluates a candidate release against a baseline, applies explicit policy thresholds, and returns a final decision of `promote` or `block` with a machine-readable audit trail.

The repository is being built as internal platform tooling for release engineering and MLOps teams.

## Goals

- compare baseline and candidate releases against the same fixture set
- detect regressions in latency, reliability, quality, and cost proxy
- apply explicit release policies instead of ad hoc judgment
- generate decision reports that CI and operators can consume

## Current Status

The current implementation includes:

- FastAPI app plus `POST /releases/evaluate`
- deterministic sample baseline and candidate services
- AI-risk fixture set and threshold policy logic
- test harness
- lightweight CI and security checks

The higher-level product writeup lives in [docs/overview.md](docs/overview.md).

## Current Capabilities

- sample baseline and candidate services for model-backed release scenarios
- deterministic AI-risk fixture evaluator
- config-backed policy profiles for different release risk tolerances
- comparison and threshold policy engine
- persisted JSON reports with policy checks and metric deltas
- FastAPI endpoint for service integration
- CLI entrypoint for local runs and CI
- automated CI check for config validation and known-good release gating
- manual GitHub Actions release-gate workflow
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

Validate local EvalGate configuration:

```bash
evalgate --validate-config
```

The validation command checks evaluation fixtures, release definitions, aliases, and policy thresholds before a release evaluation runs.

Validate a saved evaluation report:

```bash
evalgate --validate-report reports/<report_id>.json
```

Print the evaluation report JSON Schema:

```bash
evalgate --print-report-schema
```

Summarize a saved evaluation report for PR comments, dashboards, or release notes:

```bash
evalgate --summarize-report reports/<report_id>.json
evalgate --summarize-report reports/<report_id>.json --summary-format markdown
```

Review only the failed checks and cases for a saved report:

```bash
evalgate --triage-report <report_id>
evalgate --triage-report <report_id> --summary-format markdown
```

List recent reports or inspect a saved report by ID:

```bash
evalgate --list-reports
evalgate --show-report <report_id>
```

## CI Release Gate

EvalGate can be used as a CI release gate because the CLI returns nonzero exit codes for blocked releases and invalid evaluation requests.

The main CI workflow runs `evalgate --validate-config` and evaluates `baseline` against `candidate-good` so each PR exercises the known-good release gate. It validates the generated report against the report contract, publishes a Markdown summary to the GitHub Actions job summary, comments that summary on pull requests, and uploads the JSON report and report index as workflow artifacts.

This repository also includes a manual GitHub Actions workflow at `.github/workflows/evalgate-release-gate.yml`. It accepts `baseline`, `candidate`, and `policy` inputs, runs `evalgate`, validates the generated report, publishes a Markdown summary, and uploads the generated JSON report and report index as workflow artifacts.

Use `candidate-good` to exercise a passing release and `candidate-bad` to exercise the blocking path. More detail is available in [docs/ci-release-gate.md](docs/ci-release-gate.md).

## Evaluation Scenarios

The deterministic fixture set covers common model-backed service risks:

- prompt injection handling
- PII leakage prevention
- factual summarization
- unsafe financial guidance refusal
- grounded answers from retrieved context
- tool-use policy enforcement

The sample releases include `candidate-good`, `candidate-risky`, `candidate-expensive`, `candidate-low-quality`, and `candidate-bad`. `candidate-bad` is kept as a blocking demo alias for CI examples.

Evaluation cases live in `fixtures/eval_cases.json`. Deterministic release behavior lives in `services/releases.json`, so adding a sample release does not require changing the service runtime code.

The evaluator calls an inference service adapter. The repository ships a deterministic registry-backed adapter for local development and CI.

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

That artifact is intended to be the audit trail for CI and operator workflows. EvalGate also maintains a local report index for listing recent evaluations and resolving saved reports by ID. The report contract, decision semantics, CLI exit codes, failure explanations, summary output, and field descriptions are documented in [docs/report-contract.md](docs/report-contract.md).
