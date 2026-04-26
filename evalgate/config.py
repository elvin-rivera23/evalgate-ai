from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR_ENV_VAR = "EVALGATE_CONFIG_DIR"


@dataclass(frozen=True, slots=True)
class EvalGateConfigPaths:
    config_dir: Path
    fixtures_path: Path
    releases_path: Path
    policy_profiles_path: Path

    def required_files(self) -> dict[str, Path]:
        return {
            "fixtures": self.fixtures_path,
            "releases": self.releases_path,
            "policy profiles": self.policy_profiles_path,
        }


def resolve_config_dir(config_dir: str | Path | None = None) -> Path:
    configured_dir = config_dir or os.environ.get(CONFIG_DIR_ENV_VAR)
    if configured_dir is None:
        return DEFAULT_CONFIG_DIR
    return Path(configured_dir).expanduser().resolve()


def get_config_paths(config_dir: str | Path | None = None) -> EvalGateConfigPaths:
    resolved_config_dir = resolve_config_dir(config_dir)
    return EvalGateConfigPaths(
        config_dir=resolved_config_dir,
        fixtures_path=resolved_config_dir / "fixtures" / "eval_cases.json",
        releases_path=resolved_config_dir / "services" / "releases.json",
        policy_profiles_path=resolved_config_dir / "policy" / "profiles.json",
    )
