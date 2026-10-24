"""Convert a verified decode result into downloadable documents."""

import re
from datetime import datetime

from agent.models import DecodeResult


def _code_block(code: str) -> str:
    # Use a fence longer than any backtick run so the code cannot close it early.
    longest_run = max((len(run) for run in re.findall(r"`+", code)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}python\n{code.rstrip()}\n{fence}"


def to_markdown(
    decoded: DecodeResult,
    code: str,
    context: str,
    created_at: datetime,
    max_characters: int,
) -> str:
    """Return the submitted input and decode result as a Markdown document."""
    character_count = len(code) + len(context)
    context_block = _code_block(context) if context.strip() else "입력하지 않았습니다."
    what = "\n".join(f"- {item}" for item in decoded.what)
    if decoded.source:
        source = "\n".join(f"- [{item.title}]({item.url})" for item in decoded.source)
    else:
        source = "지원되는 공식 문서 출처를 찾지 못했습니다."
    return (
        "# AI Code Decode 결과\n\n"
        f"- 생성 일시: {created_at:%Y-%m-%d %H:%M:%S}\n"
        f"- 글자 수: {character_count:,} / {max_characters:,}자\n\n"
        "## 입력 코드\n\n"
        f"{_code_block(code)}\n\n"
        "## 주변 코드\n\n"
        f"{context_block}\n\n"
        f"## What\n\n{what}\n\n"
        f"## Why\n\n{decoded.why}\n\n"
        f"## Source\n\n{source}\n\n"
        f"## Example\n\n{_code_block(decoded.example)}\n\n"
        f"## Check\n\n{decoded.check}\n"
    )
