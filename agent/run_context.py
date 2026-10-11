"""Per-run state shared by the decoder's function tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agent.models import DecodePipelineEvidence


AudienceLevel = Literal["Beginner", "Developer"]


@dataclass
class DecodeRunContext:
    """Keep submitted input and verified pipeline evidence server-side."""

    code: str
    surrounding_context: str
    level: AudienceLevel
    pipeline_evidence: DecodePipelineEvidence | None = None
    tool_call_audit: list[str] = field(default_factory=list)

    def record_tool_call(self, tool_name: str) -> None:
        """Record an executed function tool for UI feedback and debugging."""
        self.tool_call_audit.append(tool_name)

    def require_pipeline_evidence(self) -> DecodePipelineEvidence:
        """Return the evidence only when the agent has called the pipeline tool."""
        if self.pipeline_evidence is None:
            raise RuntimeError("에이전트가 코드 디코드 파이프라인 도구를 호출하지 않았습니다.")
        return self.pipeline_evidence
