"""Structured input and output models used by the decoder."""

from pydantic import BaseModel, ConfigDict, Field


class LearningTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Readable name of the Python feature or API")
    kind: str = Field(description="One of function, method, import, or syntax")
    module: str = Field(description="Python module, or builtins when applicable")
    symbol: str = Field(description="Symbol name suitable for official documentation lookup")


class CodeAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imports: list[str]
    functions: list[str]
    syntax: list[str]
    learning_targets: list[LearningTarget]
    notes: list[str]


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

