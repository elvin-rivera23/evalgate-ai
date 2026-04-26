# Pilot Onboarding

This guide describes how a team can pilot EvalGate against a local or internal model-backed service without paid infrastructure. The pilot path uses local execution, GitHub Actions, HTTP service adapters, JSON report artifacts, and explicit policy profiles.

## Prerequisites

- Python 3.11
- A service endpoint that can evaluate one fixture prompt at a time
- A baseline release identifier
- A candidate release identifier
- A small fixture set with normalized expected answers
- A policy profile that reflects the service risk level

For HTTP-backed candidates, the service endpoint should implement the contract in [service-adapters.md](service-adapters.md).

## 1. Choose The Pilot Scope

Start with one service and one release path:

- baseline: current trusted release
- candidate: release under review
- policy: `default`, `strict`, `cost-sensitive`, or a service-specific profile
- fixtures: 10-30 high-signal cases that represent real release risk

The first pilot should prove the release workflow, not maximize fixture coverage.

## 2. Configure The Candidate Adapter

Add an HTTP-backed candidate release in `services/releases.json`:

```json
{
  "releases": {
    "my-service-candidate": {
      "adapter": "http",
      "endpoint": "${EVALGATE_MY_SERVICE_ENDPOINT}",
      "timeout_seconds": 10
    }
  }
}
```

Set the endpoint outside the repository:

```bash
export EVALGATE_MY_SERVICE_ENDPOINT="http://127.0.0.1:8080/evaluate"
```

PowerShell:

```powershell
$env:EVALGATE_MY_SERVICE_ENDPOINT = "http://127.0.0.1:8080/evaluate"
```

For CI, store the endpoint in a GitHub Actions secret such as `EVALGATE_MY_SERVICE_ENDPOINT`.

## 3. Add Fixtures And Policy

Customize fixtures and thresholds with [fixtures-and-policies.md](fixtures-and-policies.md):

- add or edit `fixtures/eval_cases.json`
- add or edit `policy/profiles.json`
- keep prompts synthetic or sanitized
- keep expected answers as normalized labels
- review threshold changes like release-control changes

## 4. Validate Locally

Run the configuration check:

```bash
evalgate --validate-config
```

Run a candidate evaluation:

```bash
evalgate --baseline baseline --candidate my-service-candidate --policy default
```

If EvalGate blocks the release, inspect the generated report:

```bash
evalgate --list-reports --report-candidate my-service-candidate --report-decision block
evalgate --triage-report <report_id> --summary-format markdown
evalgate --show-report <report_id>
```

Run the normal test suite before proposing changes:

```bash
pytest
```

## 5. Add CI

Copy [examples/evalgate-release-gate.yml](examples/evalgate-release-gate.yml) into the EvalGate repository or a dedicated evaluation repository that contains the service fixture, policy, and release configuration. Save it as `.github/workflows/evalgate-release-gate.yml`.

Set repository or environment secrets:

- `EVALGATE_MY_SERVICE_ENDPOINT`: service endpoint used by the HTTP adapter

Adjust workflow environment values:

```yaml
env:
  EVALGATE_BASELINE: baseline
  EVALGATE_CANDIDATE: my-service-candidate
  EVALGATE_POLICY: default
  EVALGATE_MY_SERVICE_ENDPOINT: ${{ secrets.EVALGATE_MY_SERVICE_ENDPOINT }}
```

The example workflow:

- installs EvalGate
- validates configuration
- runs the release gate
- validates the generated report
- writes a Markdown summary to the job summary
- uploads the report and report index as artifacts
- fails the job when the candidate decision is `block`

## 6. Review Pilot Output

During the pilot, review:

- `decision`: whether the release is `promote` or `block`
- failed policy checks and reasons
- failed fixture cases by severity and risk category
- report artifact contents
- report history for repeated candidate runs
- whether thresholds reflect the team's actual release tolerance

Useful commands:

```bash
evalgate --summarize-report reports/<report_id>.json --summary-format markdown
evalgate --triage-report <report_id> --summary-format markdown
evalgate --list-reports --report-candidate my-service-candidate
```

## Success Criteria

A pilot is successful when:

- teams can run EvalGate locally and in CI
- service endpoints satisfy the HTTP adapter contract
- fixtures catch meaningful regressions without excessive noise
- policy thresholds are reviewed and understood
- blocked reports are actionable from summary and triage output
- report artifacts are retained in CI for audit and review

## Security Notes

- Do not commit internal service URLs; use environment variables or secrets.
- Do not commit production prompts, customer data, tokens, credentials, or private logs.
- Keep report artifacts in CI retention systems appropriate for the service data classification.
- Review fixture and policy changes with the service owner before enforcing them as required checks.
