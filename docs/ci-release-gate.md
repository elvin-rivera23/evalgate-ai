# CI Release Gate

EvalGate can run as a CI release gate because the CLI uses exit codes that automation can enforce:

- `0`: candidate passed the selected policy and can be promoted
- `1`: candidate failed the selected policy and the workflow should block
- `2`: the evaluation request was invalid

The repository includes `.github/workflows/evalgate-release-gate.yml` as a manual GitHub Actions workflow. It installs EvalGate, evaluates a selected baseline and candidate release, and uploads the generated JSON report as a workflow artifact.

Run the workflow with the default inputs to evaluate a passing candidate:

```text
baseline: baseline
candidate: candidate-good
policy: default
```

Run it with `candidate-bad` to exercise the blocking path:

```text
baseline: baseline
candidate: candidate-bad
policy: default
```

The workflow fails when EvalGate returns `block`, which is the intended release-gate behavior.
