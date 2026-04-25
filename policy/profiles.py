from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from evalgate.errors import UnsupportedPolicyError
from policy.models import PolicyProfile, PolicyThresholds

PROFILES_PATH = Path(__file__).with_name("profiles.json")


def load_policy_profile(policy_name: str) -> PolicyProfile:
    profiles = load_policy_profiles()
    try:
        return profiles[policy_name]
    except KeyError as exc:
        raise UnsupportedPolicyError(policy_name) from exc


def load_policy_profiles() -> dict[str, PolicyProfile]:
    payload = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    return {
        name: PolicyProfile(
            name=name,
            description=profile_payload["description"],
            thresholds=build_thresholds(profile_payload["thresholds"]),
        )
        for name, profile_payload in payload.items()
    }


def build_thresholds(payload: dict[str, float]) -> PolicyThresholds:
    threshold_names = {field.name for field in fields(PolicyThresholds)}
    unexpected_names = set(payload) - threshold_names
    if unexpected_names:
        unexpected = ", ".join(sorted(unexpected_names))
        raise ValueError(f"Unsupported policy threshold fields: {unexpected}")

    return PolicyThresholds(**payload)
