"""Select the most useful explanation targets from static analysis results."""

from __future__ import annotations

from typing import Literal

from agent.documentation import is_documentable
from agent.models import (
    ExcludedLearningTarget,
    LearningPlan,
    LearningPlanItem,
    LearningTarget,
)


MAX_PRIMARY_TARGETS = 3


def _dependency_depth(
    target: LearningTarget, targets_by_name: dict[str, LearningTarget]
) -> int:
    depth = 0
    parent_name = target.used_as_input_of
    visited_names = {target.name}
    while parent_name and parent_name not in visited_names:
        parent = targets_by_name.get(parent_name)
        if parent is None:
            break
        depth += 1
        visited_names.add(parent.name)
        parent_name = parent.used_as_input_of
    return depth


def _selection_reason(target: LearningTarget) -> str:
    if target.used_as_input_of:
        return (
            f"`{target.expression}`의 결과가 `{target.used_as_input_of}`에 전달되므로 "
            "먼저 설명합니다."
        )
    if target.module == "builtins":
        return f"`{target.expression}`에서 사용한 Python 내장 기능입니다."
    return f"`{target.expression}`에서 직접 호출한 확인 가능한 API입니다."


def build_learning_plan(
    learning_targets: list[LearningTarget],
    syntax: list[str],
    level: Literal["Beginner", "Developer"],
) -> LearningPlan:
    """Create a deterministic, small explanation plan from resolved targets."""
    resolved_targets = [
        target for target in learning_targets if target.resolution == "resolved"
    ]
    targets_by_name = {target.name: target for target in resolved_targets}
    # Third-party targets cannot produce citable docs, so they only fill slots
    # left over after builtins and standard-library targets.
    documentable_ids = {
        target.target_id
        for target in resolved_targets
        if is_documentable(target.module, target.symbol)
    }
    ranked_targets = sorted(
        resolved_targets,
        key=lambda target: (
            target.target_id not in documentable_ids,
            -_dependency_depth(target, targets_by_name),
            target.source != "submitted_code",
            target.line is None,
            target.line or 0,
            target.target_id,
        ),
    )
    selected_targets = ranked_targets[:MAX_PRIMARY_TARGETS]
    selected_ids = {target.target_id for target in selected_targets}

    excluded_targets: list[ExcludedLearningTarget] = []
    for target in learning_targets:
        if target.target_id in selected_ids:
            continue
        if target.resolution == "unresolved":
            reason = "모듈 또는 심볼을 정적으로 확인할 수 없어 문서 조회에서 제외했습니다."
        elif target.target_id not in documentable_ids:
            reason = (
                "Python 공식 문서 지원 범위 밖의 대상이라 내장 기능과 표준 라이브러리보다 "
                "뒤로 미뤘습니다."
            )
        else:
            reason = (
                f"핵심 개념을 최대 {MAX_PRIMARY_TARGETS}개로 제한하기 위해 "
                "이번 설명에서 제외했습니다."
            )
        excluded_targets.append(
            ExcludedLearningTarget(target_id=target.target_id, reason=reason)
        )

    return LearningPlan(
        audience_level=level,
        primary_targets=[
            LearningPlanItem(
                target_id=target.target_id,
                explanation_order=index,
                reason=_selection_reason(target),
            )
            for index, target in enumerate(selected_targets, start=1)
        ],
        syntax_topics=syntax,
        excluded_targets=excluded_targets,
    )
