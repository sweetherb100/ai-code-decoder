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
    error_type: Optional[str] = Field(
        default=None, description="Exception class name when status is unavailable"
    )


class DecodePipelineEvidence(BaseModel):
    """Verified results returned by one deterministic decode-pipeline execution."""

    model_config = ConfigDict(extra="forbid")

    analysis: CodeAnalysis
    learning_plan: LearningPlan
    documentation: list[DocumentationEvidence]


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    url: str


class ConceptExplanation(BaseModel):
    """One planned learning target explained next to the code it came from."""

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(description="target_id of a learning_plan primary target")
    role: str = Field(
        description="[What · Fact] What this API or syntax does, grounded in code and docs"
    )
    input: str = Field(description="What the code passes in, as written in the source")
    output: str = Field(description="What comes back and where the code uses it")
    connection: str = Field(
        description=(
            "[Why · Assumption] How this target connects to surrounding lines and why "
            "it may be needed here; inferred intent must be qualified as a possibility"
        )
    )
    related_lines: list[int] = Field(
        description="One-based lines, in the same input as the target, that feed or use it"
    )
    source_id: Optional[str] = Field(
        description="source_id of this target's exact_match documentation, else null"
    )
    example: str = Field(description="A minimal Python example focused on this target only")


class QuizOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Short answer choice")
    correct: bool = Field(description="True for exactly one option")
    feedback: str = Field(
        description="Why this choice is right or wrong, pointing back to the explanation"
    )


class UnderstandingQuiz(BaseModel):
    """A one-depth multiple-choice question that predicts behavior or role."""

    model_config = ConfigDict(extra="forbid")

    question: str
    options: list[QuizOption] = Field(description="Two to four choices, exactly one correct")


class DecodeResult(BaseModel):
    """The stable What / Why / Source / Example / Check response contract.

    `concepts` and `quiz` extend it for the focus-and-check learning screens; the
    original five fields keep their meaning.
    """

    model_config = ConfigDict(extra="forbid")

    what: list[str] = Field(description="Important Python syntax and APIs in the code")
    why: str = Field(description="Context-grounded explanation; inferred intent is qualified")
    source: list[SourceReference]
    example: str
    check: str = Field(description="One question that checks the user's understanding")
    concepts: list[ConceptExplanation] = Field(
        description="One explanation per learning_plan primary target, in explanation_order"
    )
    quiz: UnderstandingQuiz
