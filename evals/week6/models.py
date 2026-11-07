"""Strict data contracts for offline evaluation artifacts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

METRICS = ("semantic_correctness", "evidence_faithfulness", "audience_fit")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalCase(StrictModel):
    case_id: str
    group_id: str
    split: Literal["dev", "holdout"]
    level: Literal["Beginner", "Developer"]
    code: str = Field(min_length=1)
    context: str = ""
    expected_outcome: Literal["success", "input_rejected"] = "success"
    facts: list[str] = Field(min_length=1)
    forbidden_claims: list[str]
    reference_urls: list[str]
    documentation_mode: Literal["live", "unavailable"] = "live"
