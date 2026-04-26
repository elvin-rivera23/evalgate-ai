# Evaluation Report Contract

EvalGate writes one JSON report for each release evaluation. The report is the durable contract between the evaluator, CI workflows, and operators reviewing a release decision.

Reports are persisted at `reports/<report_id>.json` and returned by `POST /releases/evaluate`.

The report contract is also available as JSON Schema:

```bash
evalgate --print-report-schema
```

Saved reports can be validated before ingestion by CI, dashboards, or release automation:

```bash
evalgate --validate-report reports/<report_id>.json
```

Saved reports can also be summarized for PR comments, dashboards, or release notes:

```bash
evalgate --summarize-report reports/<report_id>.json
evalgate --summarize-report reports/<report_id>.json --summary-format markdown
```

Operators can triage blocked reports by listing only failed checks, failed cases, and their supporting evidence:

```bash
evalgate --triage-report <report_id>
evalgate --triage-report <report_id> --summary-format markdown
```

EvalGate maintains a local report index at `reports/index.json` so operators can list recent evaluations and load saved reports by ID:

```bash
evalgate --list-reports
evalgate --show-report <report_id>
```

`--show-report` prints the full saved report from `reports/<report_id>.json`. If the index contains the report ID but the JSON artifact is missing, EvalGate reports that state separately from an unknown report ID.

## Decision Semantics

The `decision` field is the release gate output:

- `promote`: all configured policy checks passed
- `block`: one or more configured policy checks failed

The CLI maps that decision to process exit codes so it can be used directly in CI:

- `0`: the evaluation completed and returned `promote`
- `1`: the evaluation completed and returned `block`
- `2`: the request was invalid, such as an unsupported policy or unknown release

## Top-Level Shape

The top-level report shape is intentionally stable:

```json
{
  "report_id": "eval-...",
  "metadata": {},
  "policy": "default",
  "policy_thresholds": {},
  "decision": "promote",
  "summary": "Candidate is within the default release thresholds.",
  "checks": [],
  "failed_checks": [],
  "evidence_summary": {},
  "case_results": [],
  "baseline_metrics": {},
  "candidate_metrics": {},
  "deltas": {}
}
```

Report validation rejects unexpected fields. Contract changes that add, rename, or remove fields should be shipped as explicit schema changes with matching documentation and tests.

## Metadata

`metadata` identifies the evaluation context:

- `created_at`: UTC timestamp for report creation
- `baseline_release_id`: trusted release used as the comparison baseline
- `candidate_release_id`: release being evaluated
- `policy`: policy profile used for the evaluation
- `evalgate_version`: EvalGate package version that produced the report

## Policy Snapshot

`policy` is the active policy profile name. `policy_thresholds` is the threshold snapshot used for the run, copied into the report so later reviews do not depend on the current contents of `policy/profiles.json`.

`checks` contains every policy check. `failed_checks` contains only checks whose `status` is `failed`.

Each check includes:

- `metric`: metric evaluated by the policy
- `baseline`: baseline metric value
- `candidate`: candidate metric value
- `threshold_type`: comparison strategy used by the policy
- `threshold_value`: configured threshold
- `delta`: measured difference between candidate and baseline
- `status`: `passed` or `failed`
- `reason`: human-readable failure explanation, or `null` for passing checks

## Evidence Summary

`evidence_summary` is the operator-friendly rollup for the decision:

- `failed_checks`: failed policy metric names
- `failed_case_count`: number of failed evaluation cases
- `total_case_count`: number of evaluated cases
- `critical_failure_count`: failed cases with critical severity
- `failed_risk_categories`: risk categories represented by failed cases
- `max_latency_delta_ms`: largest per-case latency increase
- `max_cost_delta_units`: largest per-case cost increase

This section is intended for CI summaries, PR comments, release dashboards, and incident review notes.

## Case Results

`case_results` provides per-fixture evidence. Each case includes:

- `case_id`: fixture identifier
- `risk_category`: scenario category, such as prompt injection or PII leakage
- `severity`: fixture severity
- `expected_answer`: expected deterministic answer
- `baseline_answer`: baseline release answer
- `candidate_answer`: candidate release answer
- `passed`: whether the candidate matched the expected answer
- `baseline_latency_ms` and `candidate_latency_ms`: measured latency values
- `latency_delta_ms`: candidate latency minus baseline latency
- `baseline_cost_units` and `candidate_cost_units`: cost proxy values
- `cost_delta_units`: candidate cost minus baseline cost

## Metric Blocks

`baseline_metrics`, `candidate_metrics`, and `deltas` contain aggregate release-level measurements used by policy checks. `deltas` stores candidate values relative to the baseline.

These blocks are useful for automated trend tracking and dashboards. Policy outcomes should still be read from `decision`, `checks`, and `failed_checks`.

## Summary Output

`evalgate --summarize-report` validates a report and emits a compact summary for integration surfaces that should not parse the full report body.

The default JSON summary includes:

- `report_id`
- `decision`
- `policy`
- `baseline_release_id`
- `candidate_release_id`
- `summary`
- `failed_checks`
- `failure_reasons`
- `failed_case_count`
- `total_case_count`
- `critical_failure_count`
- `failed_risk_categories`

Markdown output is available with `--summary-format markdown` for PR comments and release notes.

## Failure Triage

`evalgate --triage-report <report_id>` validates the saved report and emits the subset an operator needs when a release is blocked:

- failed policy checks with human-readable reasons
- failed evaluation cases with risk category and severity
- baseline and candidate answers for each failed case
- latency and cost deltas for each failed case

The default output is JSON for automation. Markdown output is available with `--summary-format markdown` for handoff notes.

## Report Index

`reports/index.json` stores compact metadata for each saved report:

- `report_id`
- `created_at`
- `baseline_release_id`
- `candidate_release_id`
- `policy`
- `decision`
- `failed_checks`
- `failed_case_count`
- `critical_failure_count`

The index is runtime state, not source-controlled product configuration. CI and local runs can regenerate it from new evaluations. The index is not a replacement for the full report artifact; it is the lookup table for recent evaluation metadata.

## Blocked Report Example

```json
{
  "policy": "default",
  "decision": "block",
  "failed_checks": [
    {
      "metric": "quality_score",
      "baseline": 1.0,
      "candidate": 0.33,
      "threshold_type": "max_drop_percent",
      "threshold_value": 0.05,
      "delta": -0.67,
      "status": "failed",
      "reason": "quality_score dropped by 67.00% from 1 to 0.33, exceeding the allowed 5.00% drop."
    }
  ],
  "evidence_summary": {
    "failed_checks": ["quality_score"],
    "failed_case_count": 4,
    "total_case_count": 6,
    "critical_failure_count": 3,
    "failed_risk_categories": ["grounding", "pii_leakage", "prompt_injection"],
    "max_latency_delta_ms": 40.0,
    "max_cost_delta_units": 0.003
  }
}
```
