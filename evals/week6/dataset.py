"""Load synthetic cases, rejecting duplicate IDs and split leakage."""

import hashlib
import json
from pathlib import Path

from evals.week6.models import EvalCase

CASES_PATH = Path(__file__).with_name("cases.jsonl")


def load_cases(path: Path = CASES_PATH) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("dataset is empty or contains duplicate case IDs")
    groups: dict[str, str] = {}
    inputs: dict[tuple[str, str], str] = {}
    for case in cases:
        for key, mapping in ((case.group_id, groups), ((case.code, case.context), inputs)):
            if key in mapping and mapping[key] != case.split:
                raise ValueError("same input/group appears in both splits")
            mapping[key] = case.split
    return cases


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def dataset_digest(cases: list[EvalCase]) -> str:
    return digest([case.model_dump() for case in cases])
