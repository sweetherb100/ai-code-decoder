# AI Code Decode Agent

OpenAI Agents SDK와 Streamlit으로 만든 Python 코드 이해 학습 도구입니다. 코드를 실행하지 않고 AST로 구조를 찾은 뒤, Python 공식 문서의 관련 내용을 What / Why / Source / Example / Check 형식으로 설명합니다.

## 기능

- Python 코드의 import, 함수 호출, f-string, comprehension, async/await 등을 AST로 정적으로 분석합니다.
- Agents SDK 에이전트가 분석 및 공식 문서 조회 도구를 사용합니다.
- Python 내장 함수·타입과 표준 라이브러리 문서만 조회합니다. 서드파티 라이브러리는 지원하지 않는다고 표시합니다.
- 설명 수준을 Beginner 또는 Developer로 선택할 수 있습니다.
- 주변 코드를 선택적으로 붙여 넣어 Why 설명에 맥락을 제공할 수 있습니다.
- 매 실행마다 이해 확인 질문 하나를 생성합니다.
- SDK tracing은 기본 비활성화되어 있으며 앱은 코드를 데이터베이스나 파일에 저장하지 않습니다.

코드와 주변 맥락은 응답 생성을 위해 OpenAI API로 전송됩니다. 공식 문서를 가져올 때에는 식별된 모듈과 심볼에 해당하는 Python 문서 페이지를 요청합니다.

## 실행

Python 3.9 이상을 사용합니다.

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

Agents SDK trace가 필요한 경우 `OPENAI_AGENTS_ENABLE_TRACING=1`로 설정합니다. 코드와 도구 입출력이 trace에 포함될 수 있으므로 필요한 경우에만 켜세요.

## 프로젝트 구조

```text
agent/
  analyzer.py       Python AST 분석
  documentation.py  공식 Python 문서 조회
  tools.py          Agents SDK 함수 도구
  prompts.py        What/Why/Source/Example/Check 지침
  models.py         분석 및 구조화 응답 모델
  decoder.py        Agent와 Runner 구성
app.py              Streamlit 데모
```

## 학습 문서

- [OpenAI Agents SDK](docs/agents_sdk.md): 에이전트 구성, 도구, handoff, guardrails, tracing
- [OpenAI Function Calling / Tool Calling](docs/function_calling.md): 개념, Responses API 예제, 실무 설계 체크리스트
- [Responses API](docs/responses_api.md): 요청, 대화 상태, 도구, 구조화된 출력
- [Langfuse 실험](docs/langfuse_experiment.md): tracing, prompt management, dataset과 SDK experiment 연결

Agents SDK 예제는 `script/agents_sdk*.py`에서 확인할 수 있습니다. 자세한 실행 방법은 [Agents SDK 실습 문서](docs/agents_sdk.md#직접-실행해보기)를 참고하세요.
Langfuse experiment 예제는 `python script/langfuse_experiment.py`로 실행합니다. prompt와 dataset 사전 준비 방법은 [Langfuse 실습 문서](docs/langfuse_experiment.md)를 참고하세요.
Langfuse에서 prompt를 불러와 단독 실행하는 간단한 예제는 `python script/langfuse_prompt.py`입니다.
