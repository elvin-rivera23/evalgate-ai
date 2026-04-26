# EvalGate Demo

This walkthrough shows the default local demo flow. It uses deterministic sample releases, so it does not require paid model APIs or hosted infrastructure.

## Run The Demo

```bash
evalgate --demo
```

The command runs one passing candidate and one blocking candidate, persists both reports under `reports/`, prints a release summary, prints blocked-release triage, and shows recent blocked history from the report index.

## Expected Shape

The passing candidate should produce a `promote` decision:

```text
Passing candidate: `candidate-good` -> `promote` (eval-...)
```

The blocking candidate should produce a `block` decision:

```text
Blocking candidate: `candidate-bad` -> `block` (eval-...)
```

The report summary highlights the release decision and policy context:

```text
## EvalGate Report Summary

- Decision: `promote`
- Policy: `default`
- Baseline: `baseline`
- Candidate: `candidate-good`
- Failed checks: none
```

The blocked-release triage shows why a candidate needs review:

```text
## EvalGate Failure Triage

- Decision: `block`
- Failed check count: 3
- Failed case count: 4
- Critical failures: 3
```

## Pilot Pack Smoke Test

The copyable starter pack can also be validated and run directly:

```bash
evalgate --config-dir docs/examples/evalgate-pack --validate-config
evalgate --config-dir docs/examples/evalgate-pack --baseline pilot-baseline --candidate pilot-candidate --policy pilot
```

Expected result:

```text
decision: promote
policy: pilot
failed checks: none
failed cases: 0/2
```
