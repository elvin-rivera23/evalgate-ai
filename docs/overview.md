# EvalGate AI Overview

## What It Is

EvalGate AI is a release-control service for model-backed systems. It compares a trusted baseline release against a candidate release, evaluates the result against explicit policy thresholds, and returns a final decision of `promote` or `block`.

The point of the project is not model quality research. The point is operational release discipline for AI systems.

## Why It Exists

Traditional health checks are not enough for model-backed services. A release can look healthy while still being worse in ways that matter:

- slower responses
- higher error rates
- lower answer quality
- higher cost per request

EvalGate AI turns those concerns into an explicit gate that can be used locally or in CI.

## Intended Workflow

1. A baseline release and candidate release are registered.
2. Both are evaluated against the same deterministic fixture set.
3. Metrics are aggregated and compared.
4. Policy checks are applied.
5. A decision report is generated and persisted.
6. CI or an operator acts on the result.

## MVP Scope

- FastAPI orchestration service
- deterministic fixture-driven evaluator
- comparator and policy engine
- persisted JSON reports
- CLI entrypoint for CI
- one passing and one blocked demo scenario

## What This Repo Optimizes For

- clarity of release logic
- deterministic demo behavior
- portability as a hiring signal for platform, DevOps, and MLOps roles
- a repo that reads like internal tooling rather than an AI toy
