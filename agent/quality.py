"""Validate that generated decode responses are grounded in tool evidence."""

from agent.models import DecodeResult, DocumentationEvidence


class DecodeQualityError(ValueError):
    """Raised when a generated decode response is not grounded in tool evidence."""

    def __init__(self, message: str, issue_codes: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.issue_codes = issue_codes


def validate_decode_result(
    decode_result: DecodeResult, documentation: list[DocumentationEvidence]
) -> DecodeResult:
    """Reject responses with missing content or unverifiable documentation sources."""
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

    if issues:
        raise DecodeQualityError(
            "응답의 근거 검증에 실패했습니다. " + " / ".join(message for _, message in issues),
            issue_codes=tuple(dict.fromkeys(code for code, _ in issues)),
        )
    return decode_result
