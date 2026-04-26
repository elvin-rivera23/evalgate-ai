import json
from dataclasses import dataclass
from pathlib import Path

from evalgate.config import get_config_paths


@dataclass(slots=True)
class EvalCase:
    case_id: str
    risk_category: str
    severity: str
    prompt: str
    expected_answer: str


def load_eval_cases(config_dir: str | Path | None = None) -> list[EvalCase]:
    fixture_path = get_config_paths(config_dir).fixtures_path
    raw_cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    return [EvalCase(**raw_case) for raw_case in raw_cases]
