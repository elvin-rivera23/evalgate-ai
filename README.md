# EvalGate AI

EvalGate AI is a policy-driven release gate for model-backed services. It compares a candidate release against a trusted baseline, applies explicit policy thresholds, and returns a `promote` or `block` decision with a machine-readable audit trail.

It is shaped like internal platform tooling for release engineering and MLOps teams: deterministic local runs, CI integration, report artifacts, policy snapshots, failure triage, and indexed release history.

## Quick Demo

Install the package in editable mode:

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

Run the end-to-end demo:

```bash
evalgate --demo
```

The demo evaluates one passing candidate and one blocking candidate, persists both reports, prints a release summary, prints blocked-release triage, and shows recent blocked history from the report index.

Look for these sections in the output:

- `EvalGate Demo`
- `EvalGate Report Summary`
- `EvalGate Failure Triage`
- `Recent Blocked Candidate History`

The higher-level product and architecture writeup lives in [docs/overview.md](docs/overview.md).

## What It Does

- compares baseline and candidate releases against the same AI-risk fixture set
- supports deterministic sample releases and HTTP-backed service adapters
- detects regressions in latency, reliability, quality, and cost proxy
- applies config-backed policy profiles instead of ad hoc release judgment
- persists JSON decision reports with policy checks, metric deltas, and per-case evidence
- summarizes reports for CI comments, dashboards, and release notes
- triages blocked releases by failed checks, failed cases, severity, and risk category
- indexes report history for candidate, baseline, policy, and decision review

## Operator Workflow

Run a passing release gate:

```bash
evalgate --baseline baseline --candidate candidate-good --policy default
```

Run a blocking release gate:

```bash
evalgate --baseline baseline --candidate candidate-bad --policy default
```

Summarize a saved report:

```bash
evalgate --summarize-report reports/<report_id>.json --summary-format markdown
```

Triage a blocked report:

```bash
evalgate --triage-report <report_id> --summary-format markdown
```

Review recent blocked history:

```bash
evalgate --list-reports --report-candidate candidate-bad --report-decision block
```

Inspect the full report artifact:

```bash
evalgate --show-report <report_id>
```

The CLI exits with `0` for `promote`, `1` for `block`, and `2` for invalid input such as an unsupported policy.

## Development

Run tests:

```bash
pytest
```

Run the API locally:

```bash
uvicorn api.main:app --reload
```

Run a sample API evaluation:

```bash
curl -X POST http://127.0.0.1:8000/releases/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "baseline": {"release_id": "baseline"},
    "candidate": {"release_id": "candidate-bad"},
    "policy": "default"
  }'
```

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
evalgate --list-reports --report-candidate candidate-bad --report-decision block
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

HTTP-backed releases are documented in [docs/service-adapters.md](docs/service-adapters.md). They let a team point EvalGate at a local or internal service endpoint without using paid model APIs or hosted infrastructure.

Fixture and policy authoring guidance is available in [docs/fixtures-and-policies.md](docs/fixtures-and-policies.md).

## Policy Profiles

EvalGate ships with config-backed policy profiles in `policy/profiles.json`:

- `default`: balanced release gate for general model-backed services
- `strict`: tighter thresholds for high-risk services
- `cost-sensitive`: stricter cost guardrail for high-volume services
- `quality-critical`: zero-tolerance quality regression gate

Each evaluation report includes the active policy name, the threshold snapshot used for the run, all pass/fail policy checks, failed checks, baseline metrics, candidate metrics, and deltas.

Teams can customize fixture cases and policy thresholds using the authoring guidance in [docs/fixtures-and-policies.md](docs/fixtures-and-policies.md).

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
