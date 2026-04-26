# Service Adapters

EvalGate evaluates releases through a service adapter. The adapter boundary lets the evaluator run the same fixture suite against different release targets without coupling policy logic to a specific model provider, web app, or internal service.

## Built-In Adapters

EvalGate currently supports two release adapter types:

- `deterministic`: reads fixture responses from `services/releases.json`; used for local development, tests, CI, and the built-in demo.
- `http`: sends each fixture case to an HTTP endpoint; used to pilot EvalGate against a local or internal model-backed service.

## HTTP Release Configuration

Add an HTTP-backed release to `services/releases.json`:

```json
{
  "releases": {
    "my-service-local": {
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

Then evaluate it against an existing baseline:

```bash
evalgate --baseline baseline --candidate my-service-local --policy default
```

`evalgate --validate-config` checks that HTTP releases have an `http://` or `https://` endpoint and a positive timeout before an evaluation runs. If an endpoint is configured with `${VAR_NAME}` and the environment variable is not set, validation fails before any request is sent.

## HTTP Request Contract

For each fixture case, EvalGate sends a `POST` request with JSON:

```json
{
  "release_id": "my-service-local",
  "case_id": "case-001",
  "risk_category": "prompt_injection",
  "severity": "critical",
  "prompt": "User-supplied evaluation prompt",
  "expected_answer": "refuse-injection"
}
```

The endpoint should run the candidate service against `prompt` and return the normalized evaluation result.

## HTTP Response Contract

The endpoint must return JSON:

```json
{
  "answer": "refuse-injection",
  "latency_ms": 128.4,
  "cost_units": 1.2,
  "is_error": false
}
```

Required fields:

- `answer`: normalized answer label used for deterministic scoring.
- `latency_ms`: request latency in milliseconds.
- `cost_units`: cost proxy for the request.

Optional fields:

- `is_error`: boolean error marker. Defaults to `false`.

EvalGate treats malformed responses, non-JSON responses, HTTP errors, and network failures as adapter errors.

## Pilot Notes

For an internal pilot, the HTTP endpoint can be a local wrapper around a service, staging endpoint, or mock server. No paid model API or hosted infrastructure is required. Keep service URLs in environment variables rather than committing internal endpoints to the repository. The important part is keeping the endpoint response contract stable so EvalGate can produce comparable metrics, policy decisions, report artifacts, triage output, and indexed history.
