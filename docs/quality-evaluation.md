# 품질 평가 시나리오

이 문서는 Tool Calling 흐름을 변경한 뒤 수동으로 확인할 대표 입력과 기대 결과를 정리합니다.
실제 OpenAI API 호출이 필요하므로 자동화 테스트에는 포함하지 않습니다.

## 공통 확인 기준

- 분석 결과에서 해석 가능한 대상만 학습 계획의 핵심 대상으로 선택한다.
- 문서 조회는 학습 계획의 핵심 대상 최대 3개에만 수행한다.
- 최종 출처는 `exact_match` 상태인 문서의 `source_id`, 제목, URL과 정확히 일치한다.
- `page_only`, `unsupported`, `unavailable` 상태의 문서는 출처에 포함하지 않는다.

## 시나리오

| 입력 목적 | 예시 코드 | 기대 결과 |
| --- | --- | --- |
| 중첩 호출 순서 | `from pathlib import Path\nfiles = sorted(Path("images").glob("*.png"))` | `Path.glob`을 `sorted`보다 먼저 설명하고, 정확히 일치한 문서만 출처로 사용한다. |
| 문자열 문법 | `name = f"file_{index}.txt"` | f-string을 설명하고, 공식 API 출처가 없으면 출처 목록은 비어 있다. |
| 표준 라이브러리 | `from pathlib import Path\nPath("data").exists()` | `Path.exists` 문서의 상태와 출처 ID가 최종 응답에 반영된다. |
| 외부 라이브러리 | `import requests\nrequests.get("https://example.com")` | 지원 범위 밖이라고 안내하며 `requests` 문서를 출처로 만들지 않는다. |
| 확인 불가 인스턴스 | `items.append(value)` | 정적 분석으로 타입을 확인하지 못한 사실을 유지하고 출처를 꾸며내지 않는다. |
| 문법 오류 | `for item in` | LLM 호출 전에 한국어 문법 오류 메시지를 표시한다. |

## Langfuse trace 확인 기준

`LANGFUSE_ENABLED=1`로 위 시나리오를 실행한 뒤 Langfuse에서 확인합니다. 지표 정의의 원본은 [`langfuse-tracing-plan.md`](./langfuse-tracing-plan.md) 5장입니다. score 칸의 "없음"은 값이 0이 아니라 **score가 만들어지지 않아야 한다**는 뜻입니다.

| 시나리오 | `outcome` | 확인할 trace 구조 | 기대 score |
| --- | --- | --- | --- |
| 중첩 호출 순서 | `success` | `lookup_documentation` 순서가 학습 계획 순서와 같음, generation 2개 | `tool_contract_passed`·`citation_integrity_passed` true, `exact_resolution_ratio`·`citation_coverage` 기록 |
| 문자열 문법 | `success` | 문서 조회가 없으면 retriever 0개 | `exact_resolution_ratio`·`citation_coverage` 없음, `cited_source_count` 0 |
| 표준 라이브러리 | `success` | retriever input에 `pathlib`/`Path.exists`, output `status=exact_match` | `exact_resolution_ratio` 1, `cited_source_count` = exact match 수 |
| 외부 라이브러리 | `success` | retriever `status=unsupported`, **input에 `requests` 이름이 없음** | `exact_resolution_ratio` 없음 (품질 실패로 집계되지 않음) |
| 확인 불가 인스턴스 | `success` | root metadata `unresolvedTargetCount` ≥ 1, 해당 대상은 문서 조회 안 됨 | 허위 출처 없음 → `citation_integrity_passed` true |
| 문법 오류 | `input_rejected` | root·`validate_input.analyze_code`가 WARNING, generation 0개, 비용 0 | 없음 (Tool 검증 전 종료) |

### 모든 trace 공통

- trace 이름 `code-decode`, 같은 브라우저 세션의 실행은 하나의 session으로 묶인다.
- `LANGFUSE_CAPTURE_CONTENT=0`이면 입력 코드·주변 코드·모델 응답 본문이 어디에도 없다. root input은 `{codeChars, contextChars, level}`만 있다.
- remote prompt를 쓰면 generation 2개 모두 `code-decoder/system`의 버전에 연결되고 root metadata `promptSource=langfuse`이다. fallback이면 `promptVersion=fallback-…`와 `promptFallbackReason`이 남고 prompt 연결은 없다.
- 결과 아래 👍/👎를 누르면 `user_feedback` score가 생기고, 다시 누르면 새로 생기지 않고 값이 바뀐다.

### 장애 주입

| 상황 | 기대 결과 |
| --- | --- |
| Langfuse prompt 조회 실패 | 로컬 프롬프트로 정상 응답, `prompt.resolve` WARNING, `promptFallbackReason=fetch_failed` |
| docs.python.org 응답 없음 | 해당 retriever WARNING과 `errorType`, 응답은 계속 생성 |
| 잘못된 OpenAI 키 | root ERROR, `outcome=runtime_error` |
| Langfuse 키 제거 또는 서버 차단 | 앱은 정상 동작, 로그에 `event=telemetry_export_failed` 또는 `telemetry_disabled` |

### 실패 trace를 시나리오로 옮기기

기본 설정에서는 trace에 코드 원문이 없습니다. `outcome != success`인 trace를 outcome별로 모아 `issueCodes`, 문서 상태 count, `syntaxTopics`, `codeChars`를 보고 **같은 특징의 입력을 새로 작성**해 위 시나리오 표에 추가하고, 근거 trace ID를 함께 적습니다.
