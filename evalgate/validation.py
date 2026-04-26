from __future__ import annotations

from dataclasses import fields

from evalgate.errors import EvalGateError
from evaluator.fixtures import load_eval_cases
from policy.models import PolicyThresholds
from policy.profiles import load_policy_profiles
from services.registry import load_release_registry


class ConfigValidationError(EvalGateError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Config validation failed")


def validate_config() -> list[str]:
    errors: list[str] = []
    cases = load_eval_cases()
    case_ids = [case.case_id for case in cases]
    case_id_set = set(case_ids)

    if len(case_ids) != len(case_id_set):
        errors.append("Evaluation case IDs must be unique.")

    for case in cases:
        if not case.case_id:
            errors.append("Evaluation case is missing case_id.")
        if not case.risk_category:
            errors.append(f"Evaluation case {case.case_id} is missing risk_category.")
        if not case.severity:
            errors.append(f"Evaluation case {case.case_id} is missing severity.")
        if not case.prompt:
            errors.append(f"Evaluation case {case.case_id} is missing prompt.")
        if not case.expected_answer:
            errors.append(f"Evaluation case {case.case_id} is missing expected_answer.")

    releases = load_release_registry()
    for release_id, release in releases.items():
        if release.adapter == "http":
            if not release.endpoint:
                errors.append(f"Release {release_id} HTTP adapter is missing endpoint.")
            elif not release.endpoint.startswith(("http://", "https://")):
                errors.append(f"Release {release_id} HTTP endpoint must use http or https.")
            if release.timeout_seconds <= 0:
                errors.append(f"Release {release_id} HTTP timeout must be greater than 0.")
            continue

        response_ids = set(release.responses)
        missing_cases = case_id_set - response_ids
        extra_cases = response_ids - case_id_set
        if missing_cases:
            missing = ", ".join(sorted(missing_cases))
            errors.append(f"Release {release_id} is missing responses for: {missing}.")
        if extra_cases:
            extra = ", ".join(sorted(extra_cases))
            errors.append(f"Release {release_id} has responses for unknown cases: {extra}.")

        for case_id, response in release.responses.items():
            if not response.answer:
                errors.append(f"Release {release_id} response {case_id} is missing answer.")
            if response.latency_ms < 0:
                errors.append(f"Release {release_id} response {case_id} has negative latency.")
            if response.cost_units < 0:
                errors.append(f"Release {release_id} response {case_id} has negative cost.")

    profiles = load_policy_profiles()
    threshold_names = {field.name for field in fields(PolicyThresholds)}
    for profile_name, profile in profiles.items():
        thresholds = profile.thresholds
        for threshold_name in threshold_names:
            value = getattr(thresholds, threshold_name)
            if value < 0:
                errors.append(f"Policy {profile_name} threshold {threshold_name} is negative.")

    return errors


def validate_config_or_raise() -> None:
    errors = validate_config()
    if errors:
        raise ConfigValidationError(errors)
