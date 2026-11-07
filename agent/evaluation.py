"""Explicit evaluation evidence shared by app requests and dataset experiments."""

from __future__ import annotations

import hashlib
import json
import math
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from agent.models import AudienceLevel, CodeAnalysis, DocumentationEvidence, LearningPlan

if TYPE_CHECKING:
    from agent.decoder import DecodeExecution

EVALUATION_SCHEMA = "code-decoder-v2"


class EvaluationInput(BaseModel):
    """Source evidence; never contains a judge verdict or control answer label."""

    model_config = ConfigDict(extra="forbid")
    code: str
    context: str
    level: AudienceLevel
    analysis: CodeAnalysis
    learning_plan: LearningPlan
    documentation: list[DocumentationEvidence]
    documentation_hash: str
    expected_facts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    run_metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = EVALUATION_SCHEMA


def build_evaluation_input(
    code: str,
    level: AudienceLevel,
    context: str,
    execution: DecodeExecution,
    *,
    expected_facts: list[str] | None = None,
    forbidden_claims: list[str] | None = None,
) -> EvaluationInput:
    """Copy verified evidence without executing input or inventing reference content."""
    documents = [d.model_dump() for d in execution.documentation]
    content = json.dumps(documents, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return EvaluationInput(
        code=code,
        context=context,
        level=level,
        analysis=execution.analysis,
        learning_plan=execution.learning_plan,
        documentation=execution.documentation,
        documentation_hash=hashlib.sha256(content.encode()).hexdigest(),
        expected_facts=expected_facts or [],
        forbidden_claims=forbidden_claims or [],
        run_metadata=execution.run_metadata,
    )


def sample_evaluation(trace_id: str | None, raw_rate: str) -> bool:
    """Select a whole request once, preserving paired judges for selected requests."""
    rate = float(raw_rate)
    if not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("evaluation sample rate must be finite and between 0 and 1")
    if not trace_id:
        return False
    # Stable across retries/processes, independent of code, model and judgment.
    bucket = int.from_bytes(hashlib.sha256(trace_id.encode()).digest()[:8], "big")
    return bucket < int(rate * (1 << 64))
