"""Per-run state shared by the decoder's function tool."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from agent.models import CodeAnalysis, DecodePipelineEvidence


AudienceLevel = Literal["Beginner", "Developer"]


class ToolContractError(RuntimeError):
    """Raised when the agent breaks the single pipeline-tool call contract."""


@dataclass
class DecodeRunContext:
    """Keep prevalidated input and verified pipeline evidence server-side."""

    level: AudienceLevel
    analysis: CodeAnalysis
    pipeline_evidence: DecodePipelineEvidence | None = None
    pipeline_tool_call_count: int = 0
    tool_call_audit: list[str] = field(default_factory=list)

    def begin_pipeline_tool_call(self) -> None:
        """Allow exactly one pipeline-tool call during an agent run."""
        self.pipeline_tool_call_count += 1
        if self.pipeline_tool_call_count > 1:
            raise ToolContractError(
                "코드 디코드 파이프라인 도구는 실행당 한 번만 호출할 수 있습니다."
            )
        self.tool_call_audit.append("decode_code_pipeline")

    def require_pipeline_evidence(self) -> DecodePipelineEvidence:
        """Return complete evidence only after the required single tool call."""
        if self.pipeline_tool_call_count != 1:
            raise ToolContractError(
                "에이전트는 코드 디코드 파이프라인 도구를 정확히 한 번 호출해야 합니다."
            )
        if self.pipeline_evidence is None:
            raise ToolContractError("에이전트가 코드 디코드 파이프라인 도구를 호출하지 않았습니다.")

        targets_by_id = {
            target.target_id: target
            for target in self.pipeline_evidence.analysis.learning_targets
        }
        expected_documents = Counter(
            (
                targets_by_id[item.target_id].module,
                targets_by_id[item.target_id].symbol,
            )
            for item in self.pipeline_evidence.learning_plan.primary_targets
        )
        returned_documents = Counter(
            (evidence.module, evidence.symbol)
            for evidence in self.pipeline_evidence.documentation
        )
        if expected_documents != returned_documents:
            raise ToolContractError(
                "학습 계획의 대상과 문서 조회 결과가 일치하지 않습니다."
            )
        return self.pipeline_evidence
