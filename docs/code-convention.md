# Code Convention

이 저장소의 모든 Python 코드 작성·리뷰는 이 문서를 따른다.

- 기준: PEP 8(스타일), PEP 257(docstring), PEP 484·585·604(타입 힌트), PEP 20(The Zen of Python)
- 예시는 실제 코드에서 가져왔다. `# Good` / `# Bad`로 구분한다.
- 섹션 번호는 고정이다. 다른 문서가 번호로 참조하므로 새 규칙은 끝에 추가하고 기존 번호를 바꾸지 않는다.

---

## 0. 우선순위와 자동 강제

**Key: 도구가 강제하는 것은 외우지 않는다. 사람이 판단할 규칙만 이 문서에 적는다.**

우선순위:

1. [SKILL.md](../.agents/skills/ai-code-decoder-maintenance/SKILL.md)의 Project invariants (코드 미실행, 문서 근거, 개인정보)
2. 이 문서
3. PEP 8

자동 강제 (`pyproject.toml`의 `[tool.ruff]`):

```bash
pip install ruff==0.17.2
ruff format .          # 들여쓰기, 줄 길이(100), 따옴표, 줄바꿈
ruff check .           # 아래 규칙 위반 검사
ruff check . --fix     # 자동 수정 가능한 위반 수정
```

| ruff 규칙 | 강제 내용 | 관련 섹션 |
|---|---|---|
| `E`, `W` | PEP 8 스타일 | - |
| `F` | 안 쓰는 import·변수, 정의 안 된 이름 | - |
| `I` | import 그룹·정렬 | §2 |
| `UP` | `X \| None`, 내장 제네릭 | §4 |
| `B` | 변경 가능한 기본 인자 등 버그 패턴 | §13 |
| `SIM` | 단순화 가능한 코드 | §6 |
| `T20` | `print` 사용 | §8 |
| `N` | PEP 8 네이밍 | §3 |

예외는 `per-file-ignores`에만 둔다. 한 줄 예외(`# noqa: <코드>`)는 이유가 코드에서 바로 보일 때만 허용한다.

---

## 1. 모듈 구조

**Key: `agent/`는 결정적 파이프라인, `app.py`는 화면만 담당한다.**

| 모듈 | 책임 |
|---|---|
| `agent/analyzer.py` | AST 정적 분석 → `CodeAnalysis` |
| `agent/planner.py` | 학습 대상 선정 → `LearningPlan` |
| `agent/documentation.py` | 공식 문서 조회 → `DocumentationEvidence` |
| `agent/package_registry.py` | 공식 문서를 조회할 서드파티 패키지 목록 (데이터만) |
| `agent/pipeline.py` | 위 세 단계를 묶는 결정적 파이프라인 |
| `agent/tools.py`, `agent/run_context.py` | 단일 function tool과 실행별 상태 |
| `agent/decoder.py` | Agents SDK 실행, 결과 검증, trace 연결 |
| `agent/quality.py` | 응답 근거·예시 코드 검증 |
| `agent/prompts.py` | 프롬프트 로드와 config 검증 |
| `agent/observability*.py` | Langfuse tracing, 허용 필드 목록 |
| `agent/models.py` | 모듈 간 계약 모델 (§5) |
| `agent/export.py` | 결과 내보내기 |
| `app.py` | Streamlit UI (§10) |

- 비즈니스 로직은 `app.py`에 두지 않는다. 화면 표시에 필요한 가공만 둔다.
- 새 단계는 기존 흐름(분석 → 계획 → 문서 조회 → 생성·검증)에 맞는 모듈에 넣는다. 새 모듈은 책임이 기존 모듈과 겹치지 않을 때만 만든다.

파일 내부 순서:

```python
"""Module docstring."""              # 1. 모듈 docstring

from __future__ import annotations   # 2. future import

import logging                       # 3. import (§2)

from agent.models import CodeAnalysis

logger = logging.getLogger(__name__) # 4. logger

MAX_CODE_CHARACTERS = 20_000         # 5. 상수, 타입 별칭

class CodeAnalysisError(ValueError): # 6. 예외, 모델 클래스
    ...

def analyze_code(...) -> ...:        # 7. 공개 함수
    ...

def _attribute_parts(...) -> ...:    # 8. 비공개 함수 (공개 함수 근처에 둬도 됨)
    ...
```

---

## 2. import

**Key: 표준 라이브러리 / 서드파티 / 로컬(`agent`) 3그룹, 절대 경로.**

```python
# Good
import logging
import os
from collections.abc import Iterator, Mapping

from agents import set_tracing_disabled

from agent.observability_fields import APP_TAG, TRACE_NAME
```

```python
# Bad
from .observability_fields import *   # relative path, wildcard
```

- 그룹 내 정렬은 `ruff check --fix`(`I`)에 맡긴다.
- `agents`(OpenAI Agents SDK, 서드파티)와 `agent`(이 프로젝트, 로컬)를 혼동하지 않는다.
- import 순서에 의미가 있으면(예: `app.py`에서 `.env`를 먼저 로드) 이유를 주석으로 남긴다.

---

## 3. 네이밍

**Key: PEP 8을 따르고, 이름만 보고 역할을 알 수 있게 짓는다.**

| 대상 | 규칙 | 예 |
|---|---|---|
| 모듈, 함수, 변수 | `snake_case` | `lookup_documentation`, `targets_by_id` |
| 클래스, 타입 별칭 | `PascalCase` | `DecodeExecution`, `AudienceLevel` |
| 상수 | `UPPER_SNAKE_CASE` | `MAX_CODE_CHARACTERS`, `OUTCOME_BY_ERROR` |
| 모듈 내부 전용 | `_` 접두사 | `_fetch_page`, `_state` |
| boolean | `is_` / `has_` / `should_` 접두사 | `is_public`, `has_credentials` |
| 예외 | `...Error` 접미사 | `CodeAnalysisError` |
| dict 매핑 | `<값>_by_<키>` | `targets_by_id`, `OUTCOME_BY_ERROR` |

```python
# Good
is_public = evidence.status in PUBLIC_DOC_STATUSES
targets_by_id = {target.target_id: target for target in analysis.learning_targets}

# Bad
public = evidence.status in PUBLIC_DOC_STATUSES   # unclear that this is a boolean
d = {t.target_id: t for t in analysis.learning_targets}
```

- 축약어를 쓰지 않는다. 예외는 관용적인 이름뿐이다(`exc`, `env`, `url`, `id`).
- 외부 시스템이 요구하는 키 이름(Langfuse metadata의 `codeChars` 등)은 그 형식을 따른다. 그런 키는 Python 식별자가 아니라 문자열이다.

---

## 4. 타입 힌트

**Key: 공개 함수는 인자와 반환값을 모두 표기한다. 같은 타입은 한 곳에서만 정의한다.**

```python
# Good
def decode_code(
    code: str,
    level: AudienceLevel,
    context: str = "",
    *,
    session_id: str | None = None,
) -> DecodeExecution:

# Bad
def decode_code(code, level, context="", session_id=None):
```

- 새 파일은 `from __future__ import annotations`로 시작한다.
- `X | None`을 쓴다. `Optional[X]`, `Union[X, Y]`는 쓰지 않는다 (PEP 604, ruff `UP`).
- 내장 제네릭을 쓴다: `list[str]`, `dict[str, Any]`. `typing.List` 등은 쓰지 않는다 (PEP 585).
- 추상 타입은 `collections.abc`에서 가져온다: `Mapping`, `Iterator`, `Callable`.
- 고정 문자열 집합은 `Literal` 타입 별칭으로 정의한다. 같은 집합을 여러 파일에서 다시 쓰지 않는다.

```python
# Good: agent/models.py 한 곳에서 정의하고 import
AudienceLevel = Literal["Beginner", "Developer"]

# Bad: pipeline.py, run_context.py, decoder.py, planner.py에서 각각 다시 정의
level: Literal["Beginner", "Developer"]
```

- `Any`는 외부 SDK 객체처럼 타입을 정하기 어려운 경계에서만 쓴다.

---

## 5. 데이터 모델 선택

**Key: 모듈·도구·LLM 경계를 넘는 데이터는 pydantic, 내부 값은 dataclass, 경계에서 dict를 그대로 넘기지 않는다.**

| 용도 | 선택 | 예 |
|---|---|---|
| 모듈 간 계약, function tool 입출력, LLM 구조화 출력 | `pydantic.BaseModel` + `extra="forbid"` | `CodeAnalysis`, `DecodeResult` |
| 실행 결과처럼 내부에서만 쓰는 불변 값 | `@dataclass(frozen=True)` | `DecodeExecution`, `ObservabilitySettings` |
| 실행 중 바뀌는 내부 상태 | `@dataclass` | `DecodeRunContext` |
| 고정 문자열 집합 | `Literal` 타입 별칭 | `AudienceLevel` |

```python
# Good
class LearningPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    explanation_order: int
    reason: str

# Bad
def build_learning_plan(...) -> dict:
    return {"target_id": ..., "order": ...}   # contract is invisible and unvalidated
```

- LLM이 채우는 필드에는 `Field(description=...)`를 단다. description도 모델에게 주는 지시다.
- 계약 모델(`DecodeResult`, tool 스키마)을 바꾸면 `PROMPT_SCHEMA_VERSION`을 확인한다 (§12).
- frozen dataclass를 바꿀 때는 `dataclasses.replace()`로 새 값을 만든다.

---

## 6. 함수와 제어문

**Key: early return으로 중첩을 줄이고, 분석 단계는 결정적으로 유지한다.**

```python
# Good
def _sample_rate(raw: str | None) -> tuple[float, bool]:
    if not raw:
        return 1.0, False
    try:
        value = float(raw)
    except ValueError:
        return 1.0, True
    if not 0.0 <= value <= 1.0:
        return 1.0, True
    return value, False

# Bad
def _sample_rate(raw):
    if raw:
        try:
            value = float(raw)
            if 0.0 <= value <= 1.0:
                return value, False
            else:
                return 1.0, True
        except ValueError:
            return 1.0, True
    else:
        return 1.0, False
```

- 함수 하나는 한 가지 일만 한다. 이름에 "and"가 들어가야 할 것 같으면 나눈다.
- `analyzer`, `planner`, `pipeline`은 같은 입력에 같은 결과를 낸다. 시간, 난수, 전역 상태에 의존하지 않는다.
- 조회가 반복되면 `set`과 `dict`로 O(1) 조회를 한다 (`targets_by_id`).
- 3개를 넘는 선택 인자는 keyword-only(`*`)로 받는다.
- 매직 넘버는 이름 있는 상수로 둔다 (`MAX_CODE_CHARACTERS = 20_000`).

---

## 7. 예외 처리

**Key: 구체적인 예외만 잡는다. 넓은 `except`는 경계에서만, 이유와 함께 쓴다.**

예상된 실패는 의미 있는 예외 클래스로 표현한다.

```python
# Good
class CodeAnalysisError(ValueError):
    """Raised when Python source cannot be parsed or is too large."""

try:
    code_tree = ast.parse(code)
except SyntaxError as exc:
    raise CodeAnalysisError(f"Python 문법 오류 ({location}): {exc.msg}") from exc
```

- 사용자 입력 문제는 `ValueError` 계열, 계약·동작 위반은 `RuntimeError` 계열을 상속한다.
- 예외를 바꿔서 다시 던질 때는 `from exc`로 원인을 이어 둔다.
- 새 예외 클래스를 만들면 `decoder.OUTCOME_BY_ERROR`에 결과 코드를 등록할지 확인한다.

`except Exception`은 아래 경계에서만 허용하고, 이유를 주석이나 docstring에 남긴다.

| 경계 | 이유 | 예 |
|---|---|---|
| telemetry | 관측 기능이 실패해도 decode 결과는 바뀌면 안 됨 (fail-open) | `observability.py` |
| 외부 설정 fallback | 원격 프롬프트가 실패하면 로컬 프롬프트로 대체 | `prompts.resolve_instructions` |
| UI 최상위 | 사용자에게 실패를 알리고 앱은 계속 동작 | `app.py` decode 버튼 |

```python
# Bad
try:
    evidence = lookup_documentation(module, symbol)
except Exception:
    pass   # failure disappears, and the citation just goes missing
```

- 예외를 조용히 삼키지 않는다. 최소한 결과 코드, 로그 이벤트, 사용자 메시지 중 하나로 남긴다.

---

## 8. 로깅과 관측성

**Key: `logging`만 쓴다. 사용자 코드와 예외 메시지는 로그와 trace에 남기지 않는다.**

```python
# Good
logger = logging.getLogger(__name__)
log_event("telemetry_init_failed", error=type(exc).__name__)

# Bad
print(f"init failed: {exc}")                      # print, raw message
logger.warning("lookup failed: %s", str(exc))      # str(exc) may echo user code or API responses
```

- `print`는 `scripts/`의 CLI 출력에만 허용한다 (ruff `T20`).
- 예외는 `type(exc).__name__`만 기록한다.
- trace의 input, output, metadata에는 길이, 개수, 상태 같은 구조 정보만 넣는다. 새 필드는 `observability_fields.py`의 허용 목록에 추가한다.
- 서드파티 패키지명은 사용자의 비공개 패키지일 수 있다. 공개 Python 대상일 때만 기록한다 (`pipeline._traced_lookup` 참고).
- 로그 메시지는 `logger.warning("event=%s", value)`처럼 `%` 인자로 넘긴다. f-string으로 미리 포맷하지 않는다.

---

## 9. 주석과 docstring

**Key: 코드·주석·docstring은 영어, 사용자에게 보이는 문자열은 한국어. 주석은 "무엇"이 아니라 "왜"를 쓴다.**

| 대상 | 언어 |
|---|---|
| 식별자, 주석, docstring | 영어 |
| UI 문구, 사용자에게 보이는 예외 메시지, 내보내는 Markdown 본문 | 한국어 |
| 커밋 메시지, README, `docs/` | 한국어 |

docstring (PEP 257):

- 모든 모듈은 첫 줄에 모듈 docstring을 둔다.
- 공개 함수, 클래스, 예외는 한 줄 docstring을 단다. 명령형이나 "Return ..." 형태로 쓰고 마침표로 끝낸다.
- 비공개 함수는 이름만으로 의도가 드러나지 않을 때만 docstring을 단다.
- 모듈 전체에 걸친 정책(예: telemetry fail-open)은 모듈 docstring에 쓴다.

```python
# Good: explains why
# Fail closed: a missing environment is "unknown", never "local", so raw
# content capture needs an explicit LANGFUSE_TRACING_ENVIRONMENT=local.
environment = env.get("LANGFUSE_TRACING_ENVIRONMENT") or "unknown"

# Bad: repeats the code
# get environment from env
environment = env.get("LANGFUSE_TRACING_ENVIRONMENT") or "unknown"
```

커밋 전 정리:

- 주석 처리한 코드는 삭제한다. 기록은 git에 남아 있다.
- TODO와 디버그 출력은 남기지 않는다. 할 일은 이슈나 PR 설명에 쓴다.

---

## 10. Streamlit (`app.py`)

**Key: 화면 상태는 `st.session_state`에 명시적 키로 두고, 비공개 렌더링 함수로 나눈다.**

- 화면 블록은 `_render_<영역>()` 함수로 나눈다 (`_render_feedback`, `_render_execution_evidence`).
- `session_state` 키는 `snake_case` 문자열이다. 새 키를 만들면 초기화와 정리 위치를 같이 정한다.
- 실패할 때 정리해야 하는 키들은 한 함수로 모아 지운다. 같은 `pop` 목록을 반복하지 않는다.
- 결과를 내보낼 때는 decode 당시 입력(`decode_input`)을 쓴다. 이후 입력창이 바뀌어도 결과와 입력이 어긋나지 않게 한다.
- UI 문구 매핑(`DOCUMENTATION_STATUS_LABELS`)은 모듈 상단 상수로 둔다.

---

## 11. 테스트

**Key: `python -m pytest tests`는 네트워크와 API 키 없이 통과해야 한다.**

- 실제 OpenAI, Langfuse, docs.python.org를 호출하지 않는다. `conftest.py`의 fake client와 in-memory exporter, `monkeypatch`를 쓴다.
- 사용자 코드 예시는 fixture에서도 실행하지 않는다. 문자열로만 다룬다.
- 테스트 이름은 검증하는 동작을 문장으로 쓴다: `test_<조건>_<기대 결과>`.

```python
# Good
def test_syntax_error_is_input_rejected_without_llm_calls(...):

# Bad
def test_decode_2(...):
```

- 입력만 다른 경우는 `@pytest.mark.parametrize`로 묶는다.
- 개인정보 관련 동작(원문 미전송 등)은 canary 문자열(`CANARY`)이 export 결과에 없는지 검사한다.
- 예외 검사는 구체적인 타입으로 한다: `pytest.raises(CodeAnalysisError)`. `pytest.raises(Exception)`은 쓰지 않는다 (ruff `B017`).

---

## 12. 프롬프트와 스키마 변경

**Key: 계약이 바뀌면 SKILL.md 절차를 따른다. 이 문서에 절차를 복제하지 않는다.**

- `DecodeResult`, function tool 계약, 프롬프트 변수, 출력 구조가 바뀌면 `PROMPT_SCHEMA_VERSION`과 README의 "Prompt 관리" 절차를 확인한다.
- 사용자에게 보이는 동작이 바뀌면 `docs/quality-evaluation.md`의 시나리오를 확인한다.
- 자세한 절차: [SKILL.md](../.agents/skills/ai-code-decoder-maintenance/SKILL.md) "Before changing code" 4번, "Implement and verify" 3번

---

## 13. 금지 목록

| 금지 | 이유 | 강제 |
|---|---|---|
| 사용자 코드에 `exec`, `eval`, `compile` 후 실행, `import` | 사용자 코드는 데이터임 (SKILL.md invariant) | 리뷰 |
| 변경 가능한 기본 인자 (`def f(x=[])`) | 호출 사이에 값이 공유됨 | ruff `B006` |
| `from x import *` | 이름 출처가 사라짐 | ruff `F403` |
| `print` (`scripts/` 제외) | §8 | ruff `T20` |
| 이유 없는 `except Exception` / `except:` | §7 | 리뷰, ruff `E722` |
| 로그·trace에 `str(exc)`, 사용자 코드, 모델 응답 원문 | §8 | 리뷰 |
| 도구가 반환하지 않은 출처 ID·URL 생성 | 출처 무결성 (SKILL.md invariant) | `quality.py` 검증 |
| 주석 처리한 코드, TODO, 디버그 출력 | §9 | 리뷰 |

---

## 부록 A. 현재 위반 사항 (2026-10-25 기준)

이 문서를 도입한 시점에 `ruff check .`에서 95건, `ruff format --check .`에서 15개 파일이 걸렸다. 수정은 기능 변경과 분리해 별도 커밋으로 한다. 이 부록은 정리가 끝나면 삭제한다.

| 항목 | 규칙 | 위치 | 자동 수정 |
|---|---|---|---|
| `Optional[X]` 사용 (35건) | §4, `UP045` | `observability.py` 15, `prompts.py` 11, `decoder.py` 4, `models.py` 4, `quality.py` 1 | O |
| import 정렬 (13건) | §2, `I001` | `agent/` 대부분, `app.py`, `tests/` | O |
| `typing.Callable` | §4, `UP035` | `tests/conftest.py` | O |
| 자리표시자 없는 f-string | `F541` | `agent/prompts.py:18` | O |
| 안 쓰는 import | `F401` | `tests/test_decode_tracing.py:13` | O |
| 한 줄 100자 초과 (40건) | `E501` | 대부분 `tests/test_decode_tracing.py`의 fixture 인자 목록 | 대부분 `ruff format`으로 해결 |
| 중첩 `with` (3건) | `SIM117` | `observability.py:363`, `tests/test_decode_tracing.py:403`, `tests/test_observability.py:91` | 일부 |
| `pytest.raises(Exception)` | §11, `B017` | `tests/test_decode_tracing.py:393` | X |
| `AudienceLevel` 중복 정의 | §4 | `pipeline.py`, `run_context.py`에 별칭, `decoder.py`, `planner.py`, `models.py`에 `Literal` 직접 사용 | X |
| 같은 `session_state.pop` 목록 반복 | §10 | `app.py` decode 예외 처리 | X |
| 이유 주석 없는 `except Exception` | §7 | `app.py` `_api_key()` | X |
| 공개 함수 docstring 누락 | §9 | `decoder.outcome_for` | X |

정리 순서 제안:

1. `ruff format .`: 모양만 바뀌므로 단독 커밋
2. `ruff check . --fix`: 자동 수정 커밋
3. 나머지 수동 항목
