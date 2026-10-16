## ✅ 변경 사항

### 1. 추적 가능한 AST 분석 결과 확장

- 각 학습 대상에 안정적인 `target_id`를 부여했습니다.
- 원본 표현식, 입력 출처, 줄 번호, 정적 해석 여부, 상위 호출 관계를 함께 저장하도록 변경했습니다.
- 제출 코드와 주변 문맥을 구분해 설명 근거로 활용하도록 변경했습니다.

### 2. 결정론적 학습 계획 추가

- 분석 결과에서 정적으로 해석 가능한 핵심 대상을 최대 3개 선정합니다.
- 중첩 호출 관계를 고려해 설명 순서를 정합니다.
- 선택되지 않거나 해석할 수 없는 대상도 제외 사유를 남깁니다.

```text
AST 분석 결과
  → 핵심 학습 대상 선정
  → 설명 순서 결정
  → 선택된 대상만 문서 조회
```

### 3. 문서 근거 상태 및 최종 출처 검증 추가

공식 문서 조회 결과를 다음 상태로 구분합니다.

- `exact_match`: 요청한 심볼의 문서 발췌를 정확히 확인
- `page_only`: 문서 페이지는 확인했지만 심볼 발췌를 찾지 못함
- `unsupported`: 지원 범위 밖 대상
- `unavailable`: 문서 조회 실패

최종 응답의 `source`에는 `exact_match` 상태의 `source_id`, 제목, URL과 정확히 일치하는 출처만 포함할 수 있도록 검증합니다.

### 4. 상위 Function Tool 기반의 하이브리드 구조로 변경

분석·계획·문서 조회가 항상 함께 필요한 흐름이므로, 개별 단계를 LLM이 선택하는 방식 대신 하나의 상위 Tool로 통합했습니다.

```text
Agent
  ↓
decode_code_pipeline Function Tool
  ├─ AST 정적 분석
  ├─ 학습 계획 생성
  └─ 공식 Python 문서 조회
  ↓
검증된 JSON 근거 반환
  ↓
Agent 최종 설명 생성
  ↓
출처·응답 품질 검증
```

기존에 개별 단계로 분리되어 있던 `analyze_code`, `build_learning_plan`, `lookup_documentation`은 이제 LLM에 개별 선택지를 주는 Function Tool이 아니라, `decode_code_pipeline` 내부에서 순서대로 실행되는 Python 함수입니다.

이는 OpenAI Function Calling 문서의 [Best practices for defining functions](https://developers.openai.com/api/docs/guides/function-calling/#best-practices-for-defining-functions) 중, 항상 순차적으로 호출되는 함수는 하나의 함수 호출로 결합하라는 권장을 참고한 설계입니다.

### 5. Tool Calling 제어 및 Tool 계약 보강

`decode_code_pipeline`은 다음 정책으로 제어합니다.

- `@function_tool(..., strict_mode=True)`로 등록
- `tool_choice="decode_code_pipeline"`으로 상위 Tool 호출 강제
- `parallel_tool_calls=False`로 병렬 호출 차단
- 서버 측 Run Context에서 Tool 호출 횟수를 정확히 1회로 검증
- Tool 미호출·중복 호출·학습 계획과 문서 결과 불일치 시 실패 처리

Tool description에는 다음을 명시했습니다.

- 읽기 전용이며 제출 코드를 실행·수정·저장하지 않음
- 언제 사용하고 언제 사용하지 않는지
- 내부 고정 실행 순서
- 반환 JSON 구조
- 문서 상태별 해석 및 인용 가능 여부
- 모델 인자가 아닌 신뢰 가능한 Run Context에서 입력을 읽는다는 점

### 6. 실행 근거 UI 추가

최종 응답과 함께 다음 정보를 확인할 수 있습니다.

- `decode_code_pipeline` Function Tool의 1회 호출 여부
- Tool 내부의 고정 파이프라인 단계
- 선택된 학습 대상과 설명 순서
- 문서 조회 상태
- Agents tracing 활성화 여부

내부 AST 분석·학습 계획·문서 조회 단계는 별도의 LLM Tool 호출이 아니라, 상위 Tool 내부의 고정 파이프라인임을 UI에서도 구분해 표시합니다.

## ✅ 향후 확장 검토 사항

현재 기능은 “Python 코드 분석 및 설명” 하나이며, 분석·계획·문서 조회는 모두 필수 단계입니다. 따라서 현재 PR에서는 상위 Agent의 자율 Tool 선택이나 Sub Agent를 추가하지 않았습니다.

서로 다른 업무나 실질적인 Tool 선택지가 생기면 아래 방향을 검토할 수 있습니다.

- 코드 리팩터링 제안
- 에러 로그 분석
- 테스트 코드 생성
- 외부 라이브러리 API 조사
- 상위 Agent의 업무별 Tool 자율 선택
- 특정 단계의 Sub Agent 및 하위 Tool 선택
- Tool Search / Tool Namespace
