from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evalgate.errors import UnknownReleaseError

REGISTRY_PATH = Path(__file__).with_name("releases.json")


@dataclass(frozen=True, slots=True)
class ReleaseResponse:
    answer: str
    latency_ms: float
    cost_units: float


@dataclass(frozen=True, slots=True)
class ReleaseDefinition:
    release_id: str
    responses: dict[str, ReleaseResponse]


def load_release_registry() -> dict[str, ReleaseDefinition]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    releases = {
        release_id: build_release_definition(release_id, release_payload)
        for release_id, release_payload in payload["releases"].items()
    }

    for alias, target in payload.get("aliases", {}).items():
        try:
            target_release = releases[target]
        except KeyError as exc:
            raise ValueError(f"Unknown release alias target: {target}") from exc
        releases[alias] = ReleaseDefinition(
            release_id=alias,
            responses=target_release.responses,
        )

    return releases


def get_release_definition(release_id: str) -> ReleaseDefinition:
    releases = load_release_registry()
    try:
        return releases[release_id]
    except KeyError as exc:
        raise UnknownReleaseError(release_id) from exc


def build_release_definition(
    release_id: str,
    payload: dict[str, object],
) -> ReleaseDefinition:
    responses_payload = payload["responses"]
    if not isinstance(responses_payload, dict):
        raise ValueError(f"Release responses must be an object: {release_id}")

    return ReleaseDefinition(
        release_id=release_id,
        responses={
            case_id: ReleaseResponse(**response_payload)
            for case_id, response_payload in responses_payload.items()
        },
    )
