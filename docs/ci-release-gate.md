# CI Release Gate

EvalGate can run as a CI release gate because the CLI uses exit codes that automation can enforce:

- `0`: candidate passed the selected policy and can be promoted
- `1`: candidate failed the selected policy and the workflow should block
- `2`: the evaluation request was invalid

The main CI workflow runs EvalGate automatically for every pull request and push covered by CI. That automated check validates config and evaluates the known-good path:

```text
baseline: baseline
candidate: candidate-good
policy: default
```

The automated check uses `candidate-good` because CI should prove EvalGate can run and pass for a valid release. A blocking candidate would intentionally fail every pull request.

The repository also includes `.github/workflows/evalgate-release-gate.yml` as a manual GitHub Actions workflow. It installs EvalGate, evaluates a selected baseline and candidate release, and uploads the generated JSON report as a workflow artifact.

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
