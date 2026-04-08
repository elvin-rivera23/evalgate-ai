import json
from dataclasses import dataclass
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "eval_cases.json"


@dataclass(slots=True)
class EvalCase:
    case_id: str
    prompt: str
    expected_answer: str


def load_eval_cases() -> list[EvalCase]:
    raw_cases = json.loads(FIXTURE_PATH.read_text())
    return [EvalCase(**raw_case) for raw_case in raw_cases]
