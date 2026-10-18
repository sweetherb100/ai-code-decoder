# AI Code Decode Agent

OpenAI Agents SDK와 Streamlit으로 만든 Python 코드 이해 학습 도구입니다. 코드를 실행하지 않고 AST로 구조를 찾은 뒤, Python 공식 문서의 관련 내용을 What / Why / Source / Example / Check 형식으로 설명합니다.

## 기능

- Python 코드의 import, 함수 호출, f-string, comprehension, async/await 등을 AST로 정적으로 분석합니다.
- 분석 결과에서 핵심 개념을 최대 3개 선정하고 설명 순서를 만듭니다.
- 앱이 분석 → 학습 계획 → 공식 문서 조회 순서로 도구 흐름을 실행한 뒤, Agents SDK 에이전트가 결과를 설명합니다.
- 문서 조회 결과는 정확한 심볼 일치, 페이지 단위 일치, 미지원, 일시적 조회 실패 상태로 구분합니다.
- 최종 답변은 실제 도구가 반환한 정확한 문서 근거만 출처로 표시하도록 검증합니다.
- Python 내장 함수·타입과 표준 라이브러리 문서만 조회합니다. 서드파티 라이브러리는 지원하지 않는다고 표시합니다.
- 설명 수준을 Beginner 또는 Developer로 선택할 수 있습니다.
- 주변 코드를 선택적으로 붙여 넣어 Why 설명에 맥락을 제공할 수 있습니다.
- 매 실행마다 이해 확인 질문 하나를 생성합니다.
- Langfuse tracing은 기본 비활성화되어 있습니다. 켜면 실행 구조·모델 사용량·검증 결과를 기록하되, 기본 설정에서는 코드 원문을 보내지 않습니다.
- 앱 자체는 코드를 데이터베이스나 파일에 저장하지 않습니다.

코드와 주변 맥락은 응답 생성을 위해 OpenAI API로 전송됩니다. 공식 문서를 가져올 때에는 식별된 모듈과 심볼에 해당하는 Python 문서 페이지를 요청합니다.

## 실행

Python 3.11 이상을 사용합니다. (Langfuse Python SDK v5 요구사항)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`의 `OPENAI_API_KEY`에 OpenAI API 키를 설정한 뒤 실행합니다.

```bash
streamlit run app.py
```

`OPENAI_MODEL`로 사용할 모델을 바꿀 수 있습니다. 기본값은 `gpt-4.1-mini`입니다. Streamlit 배포에서는 환경 변수 또는 `.streamlit/secrets.toml`에 `OPENAI_API_KEY`를 설정하세요.

검증된 버전 조합으로 설치하려면 `pip install -r requirements-lock.txt`를 사용합니다.

### Langfuse tracing

`.env`에 `LANGFUSE_ENABLED=1`과 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`을 모두 설정하면 켜집니다. Decode 1회가 Langfuse trace 1개로 기록되고, 같은 브라우저 세션의 실행은 하나의 session으로 묶입니다. Tool 계약·출처 검증 통과 여부, 문서 근거 비율 같은 품질 점수가 자동으로 기록되고, 결과 아래 👍/👎를 누르면 사용자 피드백 점수도 같은 trace에 남습니다.

데이터 전송·저장 정책:

- 앱 자체 DB나 파일에는 코드를 저장하지 않습니다.
- 응답 생성을 위해 코드와 주변 코드는 OpenAI API로 전송됩니다.
- Langfuse에는 기본적으로 **원문 없이** 길이, 분석 대상 수, 문서 조회 상태, 검증 결과, 모델·토큰·지연 시간만 기록합니다. 외부 패키지명, 예외 메시지, 모델 응답 본문도 보내지 않습니다.
- `LANGFUSE_CAPTURE_CONTENT=1`은 `LANGFUSE_TRACING_ENVIRONMENT=local`일 때만 적용되며, 이때는 코드와 응답 원문이 Langfuse에 저장될 수 있습니다. 다른 환경에서는 자동으로 0으로 바뀝니다.
- OpenAI 플랫폼 trace로는 전송하지 않습니다. tracing을 끄면 Agents SDK trace 자체를 만들지 않습니다.

### Prompt 관리

시스템 프롬프트는 Langfuse의 `code-decoder/system`(text prompt)에서 `LANGFUSE_PROMPT_LABEL`(기본 `production`) label 버전을 읽어 씁니다. 해당 버전이 모든 LLM 호출(generation)에 연결되므로 Langfuse에서 프롬프트 버전별 품질·비용을 비교할 수 있습니다.

- 조회 실패, prompt 형식·`schemaVersion`·config 오류가 있으면 `agent/prompts.py`의 로컬 프롬프트 전체로 대체합니다. 이때 trace에는 `promptVersion=fallback-<hash>`와 대체 사유가 남습니다.
- 새 버전 만들기: `python scripts/seed_prompts.py --message "변경 내용"` → `staging` label로만 생성됩니다. `LANGFUSE_PROMPT_LABEL=staging`으로 확인한 뒤 Langfuse UI에서 `production` label을 옮겨 배포하고, 되돌릴 때는 이전 버전으로 label을 옮깁니다.
- `DecodeResult` 형식이나 Tool 계약이 바뀌면 `PROMPT_SCHEMA_VERSION`을 올리고 새 버전을 seed합니다. 이전 schema의 원격 프롬프트는 자동으로 무시됩니다.

설계 문서: [`docs/langfuse-tracing-plan.md`](docs/langfuse-tracing-plan.md)

### 테스트

```bash
pip install pytest
python -m pytest tests
```

테스트는 OpenAI 응답을 HTTP 계층에서 흉내 내고 Langfuse export를 메모리로 받아, 실제로 내보내질 span에 원문이 없는지와 trace 구조를 검증합니다.

## 프로젝트 구조

```text
agent/
  analyzer.py       Python AST 분석
  planner.py        학습 대상 우선순위와 설명 순서 선정
  workflow.py       분석·계획·문서 조회 순서 강제
  documentation.py  공식 Python 문서 조회
  quality.py        최종 응답의 문서 근거 검증
  tools.py          Agents SDK 함수 도구
  prompts.py        로컬 프롬프트·config와 Langfuse 프롬프트 조회/대체
  models.py         분석 및 구조화 응답 모델
  decoder.py        Agent와 Runner 구성, decode trace root
  observability.py  Langfuse 초기화, observation·score helper, export masking
  observability_fields.py  trace에 내보내는 metadata·score·속성 registry
app.py              Streamlit 데모
```
