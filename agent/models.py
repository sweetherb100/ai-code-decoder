"""Structured input and output models used by the decoder."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LearningTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(description="Stable identifier for this analysis result")
    name: str = Field(description="Readable name of the Python feature or API")
    kind: str = Field(description="One of function, method, import, or syntax")
    module: str = Field(description="Python module, or builtins when applicable")
    symbol: str = Field(description="Symbol name suitable for official documentation lookup")
    expression: str = Field(description="Source expression that produced this target")
    source: Literal["submitted_code", "surrounding_context"] = Field(
        description="Which submitted input contains the expression"
    )
    line: Optional[int] = Field(
        description="One-based source line containing the expression"
    )
    end_line: Optional[int] = Field(
        description="One-based final source line of the expression"
    )
    resolution: Literal["resolved", "unresolved"] = Field(
        description="Whether static analysis resolved a module and symbol"
    )
    used_as_input_of: Optional[str] = Field(
        description="Direct enclosing call that receives this call result, when known"
    )


class CodeAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imports: list[str]
    functions: list[str]
    syntax: list[str]
    learning_targets: list[LearningTarget]
    notes: list[str]


class LearningPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    explanation_order: int
    reason: str


class ExcludedLearningTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    reason: str


class LearningPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience_level: Literal["Beginner", "Developer"]
    primary_targets: list[LearningPlanItem]
    syntax_topics: list[str]
    excluded_targets: list[ExcludedLearningTarget]


class DocumentationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    status: Literal["exact_match", "page_only", "unsupported", "unavailable"]
    module: str
    symbol: str
    title: str
    excerpt: str
    url: str


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    url: str


class DecodeResult(BaseModel):
    """The stable What / Why / Source / Example / Check response contract."""

    model_config = ConfigDict(extra="forbid")

    what: list[str] = Field(description="Important Python syntax and APIs in the code")
    why: str = Field(description="Context-grounded explanation; inferred intent is qualified")
    source: list[SourceReference]
    example: str
    check: str = Field(description="One question that checks the user's understanding")
