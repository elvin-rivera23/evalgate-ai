# Changelog

## 0.2.0 - 2026-04-26

EvalGate 0.2.0 is the pilot-ready foundation release.

### Added

- CLI and API release evaluation for baseline and candidate releases.
- Deterministic fixture evaluation with policy-backed `promote` and `block` decisions.
- Config-backed policy profiles for default, strict, cost-sensitive, and quality-critical gates.
- JSON report artifacts, report schema validation, report summaries, failure triage, and report history lookup.
- GitHub Actions release-gate workflow with report validation, PR summaries, artifacts, gitleaks, dependency review, CodeQL, linting, and cross-platform tests.
- HTTP service adapter for evaluating local or internal model-backed services.
- External evaluation pack support with `--config-dir` and `EVALGATE_CONFIG_DIR`.
- Pilot onboarding, service adapter, fixture authoring, CI, report contract, and architecture documentation.

### Security

- Internal endpoints can be supplied through environment variables or GitHub Actions secrets.
- Repository CI runs gitleaks and dependency review.
- Report artifacts and fixtures are documented with guidance to avoid credentials, private prompts, customer data, and internal URLs.
