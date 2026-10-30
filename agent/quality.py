"""Validate that generated decode responses are grounded in tool evidence."""

from typing import Optional, Sequence

from agent.models import DecodeResult, DocumentationEvidence, LearningTarget


MIN_QUIZ_OPTIONS = 2
MAX_QUIZ_OPTIONS = 4


class DecodeQualityError(ValueError):
    """Raised when a generated decode response is not grounded in tool evidence."""

    def __init__(self, message: str, issue_codes: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.issue_codes = issue_codes


def is_single_question_format(check: str) -> bool:
    """Return whether `check` has exactly one question mark (format only, not semantics)."""
    return check.count("?") + check.count("？") == 1


def validate_decode_result(
    decode_result: DecodeResult,
    documentation: list[DocumentationEvidence],
    primary_targets: Optional[Sequence[LearningTarget]] = None,
) -> DecodeResult:
    """Reject responses with missing content or unverifiable documentation sources.

    When `primary_targets` is given, each concept must explain one of them and may
    cite only that target's own exact_match documentation.
    """
    issues: list[tuple[str, str]] = []
    required_fields = {
        "what": bool(decode_result.what),
        "why": bool(decode_result.why.strip()),
        "example": bool(decode_result.example.strip()),
        "check": bool(decode_result.check.strip()),
    }
    missing_fields = [
        field_name for field_name, is_present in required_fields.items() if not is_present
    ]
    if missing_fields:
        issues.append(("missing_field", f"필수 응답 항목 누락: {', '.join(missing_fields)}"))
    if required_fields["check"] and not is_single_question_format(decode_result.check):
        issues.append(("invalid_check_format", "확인 질문은 물음표가 하나인 질문 하나여야 합니다"))

    exact_evidence = {
        evidence.source_id: evidence
        for evidence in documentation
        if evidence.status == "exact_match"
    }
    if exact_evidence and not decode_result.source:
        issues.append(("missing_source", "정확히 확인된 문서 근거가 있지만 출처가 없습니다"))
    if not exact_evidence and decode_result.source:
        issues.append(("unexpected_source", "정확히 확인된 문서 근거 없이 출처를 포함했습니다"))

    seen_source_ids: set[str] = set()
    for source in decode_result.source:
        if source.source_id in seen_source_ids:
            issues.append(("duplicate_source", f"출처가 중복되었습니다: {source.source_id}"))
            continue
        seen_source_ids.add(source.source_id)
        evidence = exact_evidence.get(source.source_id)
        if evidence is None:
            issues.append(("unverified_source", f"검증되지 않은 출처입니다: {source.source_id}"))
            continue
        if source.title != evidence.title or source.url != evidence.url:
            issues.append(
                ("source_info_mismatch", f"도구 결과와 다른 출처 정보입니다: {source.source_id}")
            )

    issues.extend(_concept_issues(decode_result, exact_evidence, primary_targets))
    issues.extend(_quiz_issues(decode_result))

    if issues:
        raise DecodeQualityError(
            "응답의 근거 검증에 실패했습니다. " + " / ".join(message for _, message in issues),
            issue_codes=tuple(dict.fromkeys(code for code, _ in issues)),
        )
    return decode_result


def _concept_issues(
    decode_result: DecodeResult,
    exact_evidence: dict[str, DocumentationEvidence],
    primary_targets: Optional[Sequence[LearningTarget]],
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    targets = (
        {target.target_id: target for target in primary_targets}
        if primary_targets is not None
        else None
    )
    seen: set[str] = set()
    for concept in decode_result.concepts:
        if concept.target_id in seen:
            issues.append(("duplicate_concept", f"같은 학습 대상을 두 번 설명했습니다: {concept.target_id}"))
            continue
        seen.add(concept.target_id)
        if not concept.role.strip() or not concept.connection.strip():
            issues.append(("missing_field", f"개념 설명 항목 누락: {concept.target_id}"))
        target = targets.get(concept.target_id) if targets is not None else None
        if targets is not None and target is None:
            issues.append(("unknown_concept_target", f"학습 계획에 없는 대상입니다: {concept.target_id}"))
            continue
        if concept.source_id is None:
            continue
        evidence = exact_evidence.get(concept.source_id)
        if evidence is None or (
            target is not None
            and (evidence.module, evidence.symbol) != (target.module, target.symbol)
        ):
            issues.append(
                ("unverified_concept_source", f"개념에 연결된 출처를 확인할 수 없습니다: {concept.target_id}")
            )
    return issues


def _quiz_issues(decode_result: DecodeResult) -> list[tuple[str, str]]:
    quiz = decode_result.quiz
    options = quiz.options
    valid = (
        bool(quiz.question.strip())
        and MIN_QUIZ_OPTIONS <= len(options) <= MAX_QUIZ_OPTIONS
        and sum(option.correct for option in options) == 1
        and all(option.label.strip() and option.feedback.strip() for option in options)
        and len({option.label.strip() for option in options}) == len(options)
    )
    if valid:
        return []
    return [("invalid_quiz", "이해도 점검은 보기 2~4개 중 정답이 하나인 객관식이어야 합니다")]


def drop_unverifiable_concepts(
    decode_result: DecodeResult,
    documentation: list[DocumentationEvidence],
    primary_targets: Sequence[LearningTarget],
) -> tuple[DecodeResult, tuple[str, ...]]:
    """Remove concept content that cannot be tied to evidence, instead of failing.

    A concept about a target outside the learning plan (often a syntax topic such as
    async/await) or a repeated target is dropped; a concept citation that is not this
    target's exact_match evidence is cleared so the UI shows "no verified source".
    Nothing is invented: content is only removed. Returns the issue codes repaired.
    """
    targets = {target.target_id: target for target in primary_targets}
    exact = {
        (evidence.module, evidence.symbol): evidence.source_id
        for evidence in documentation
        if evidence.status == "exact_match"
    }
    repaired: list[str] = []
    kept = []
    seen: set[str] = set()
    for concept in decode_result.concepts:
        target = targets.get(concept.target_id)
        if target is None:
            repaired.append("unknown_concept_target")
            continue
        if concept.target_id in seen:
            repaired.append("duplicate_concept")
            continue
        seen.add(concept.target_id)
        if concept.source_id is not None and concept.source_id != exact.get(
            (target.module, target.symbol)
        ):
            repaired.append("unverified_concept_source")
            concept = concept.model_copy(update={"source_id": None})
        kept.append(concept)
    if not repaired:
        return decode_result, ()
    return (
        decode_result.model_copy(update={"concepts": kept}),
        tuple(dict.fromkeys(repaired)),
    )
