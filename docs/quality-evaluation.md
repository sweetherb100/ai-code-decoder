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
