# OpenAI Agents SDK

> 목적: OpenAI Agents SDK의 기본 구성 요소와 에이전트 실행 흐름을 이해하고, tool·handoff·guardrail·tracing 기능을 어떤 상황에 적용할지 익힌다.

## 한 줄로 이해하기

> **Agents SDK는 model, instructions, tools를 묶어 에이전트 실행 루프와 여러 에이전트 간 협업을 구성하는 Python 프레임워크다.**

일반적인 단일 LLM 요청은 입력에 대한 답을 한 번 생성한다. 에이전트는 작업을 진행하며 tool을 선택하고, 결과를 반영해 다음 단계를 수행한 뒤 종료 조건에 도달하면 결과를 반환한다. SDK의 `Runner`가 이 실행 루프를 관리한다.

## model, instructions, tools

OpenAI의 실용 가이드에서는 에이전트를 **model, tools, instructions**의 조합으로 소개한다. `model`이 작업의 다음 단계를 판단하고, `tools`가 데이터 조회나 외부 작업을 수행하며, `instructions`가 에이전트의 역할과 행동 규칙을 정한다. 아래 한국어 설명과 영어 용어를 함께 익혀두면 공식 문서의 용어와 코드 설정을 바로 연결할 수 있다.

| 공식 용어 | 역할 | 예시 |
| --- | --- | --- |
| `model` | 작업 흐름을 판단하고 다음 행동을 선택 | 질문에 답하거나 tool 선택 |
| `tools` | 외부 데이터 조회 또는 작업 수행 | 함수, 웹 검색, MCP 서버 |
| `instructions` | 에이전트의 역할·절차·제약을 정의 | 모르는 정보는 추측하지 않기 |

에이전트는 모든 LLM 기능에 필요한 것은 아니다. 절차가 명확하고 입력·출력이 결정적인 작업은 일반 코드나 규칙 기반 자동화가 더 단순할 수 있다. 모호한 판단, 예외가 많은 절차, 비정형 데이터가 포함된 워크플로에서 에이전트 접근이 유용할 수 있다.

## 기본 실행

다음은 SDK의 최소 형태를 보여주는 예시다. SDK 설치와 API 키 설정은 [공식 Quickstart](https://openai.github.io/openai-agents-python/quickstart/)을 따른다.

```python
from agents import Agent, Runner

agent = Agent(
    name="학습 도우미",
    instructions="질문에 간결하게 답하고, 모르는 내용은 모른다고 말하세요.",
)

result = Runner.run_sync(agent, "에이전트란 무엇인가요?")
print(result.final_output)
```

`Agent`는 `instructions`, `model`, `tools` 등을 정의한다. `Runner.run_sync`는 동기 실행 예시이며, 비동기 애플리케이션에서는 `Runner.run`을 사용할 수 있다. `Runner`는 model 응답이 tool 호출이면 tool 실행과 후속 model 호출을 이어가고, 최종 결과가 나오면 `final_output`에 제공한다.

## tools와 실행 흐름

`tools`는 에이전트가 현재 대화 바깥의 정보나 기능을 이용하게 한다. 함수 tool은 Python 함수로 정의하고, 웹 검색이나 MCP 같은 tool과 함께 에이전트에 제공할 수 있다.

```python
from agents import Agent, Runner, function_tool


@function_tool
def lookup_course(topic: str) -> str:
    """주제에 맞는 강의 자료 위치를 찾는다."""
    catalog = {
        "agents": "docs/agents_sdk.md",
        "tools": "docs/function_calling.md",
    }
    return catalog.get(topic.lower(), "자료를 찾지 못했습니다.")


agent = Agent(
    name="자료 안내 에이전트",
    instructions="자료 위치를 물으면 lookup_course를 사용하세요.",
    tools=[lookup_course],
)

result = Runner.run_sync(agent, "도구 설명 자료는 어디 있나요?")
print(result.final_output)
```

tool 설명은 model이 언제 무엇을 사용할지 판단하도록 돕는다. 실제 함수는 애플리케이션의 권한으로 실행되므로, 함수 안에서 인수와 사용자 권한, 부작용을 확인해야 한다. 특히 이메일 발송이나 데이터 변경 같은 action tool은 실행 전 확인 절차를 두는 것이 안전하다.

## 주요 SDK 기능

### 에이전트 간 작업 연결

작업이 전문 분야에 따라 나뉘면 에이전트 하나가 다른 에이전트에 일을 맡길 수 있다.

- **Handoff**: 현재 에이전트가 대화 처리를 전문 에이전트에게 넘긴다. 예를 들어 분류 에이전트가 여행 예약 요청을 여행 에이전트에 전달한다.
- **Agent as a tool**: 주 에이전트가 전문 에이전트를 tool처럼 호출하고, 결과를 받아 전체 흐름을 계속 관리한다.

여러 에이전트를 처음부터 구성하기보다 단일 에이전트와 필요한 tools로 시작하는 편이 평가와 유지 관리가 쉽다. 역할 분담이 뚜렷하거나 tools·instructions가 복잡해졌을 때 멀티 에이전트 구성을 검토한다.

### 구조화된 출력

후속 코드가 결과를 처리해야 한다면 Pydantic model 등으로 출력 형태를 정의할 수 있다. SDK는 에이전트 결과를 정해진 필드로 표현하도록 지원한다. 형식 정의는 프로그램이 결과를 다루기 쉽게 하지만, 그 값이 사실인지까지 보증하지는 않으므로 필요한 검증은 애플리케이션에서 수행한다.

### Context

`context`는 실행 중 tool과 훅 등에 애플리케이션 데이터를 전달하는 방법이다. 사용자 세션, 데이터베이스 연결, 요청별 상태처럼 model 프롬프트에 그대로 넣을 필요가 없는 런타임 정보를 전달하는 데 쓸 수 있다. model에 보여줄 대화 내용 및 `instructions`와 애플리케이션 런타임 상태를 구분해 설계한다.

### Guardrails

Guardrail은 입력이나 출력을 검사해 정책에 맞지 않는 처리를 차단하거나 흐름을 중단하는 검증 장치다. `instructions`만으로 안전을 보장하려 하지 말고, 민감한 동작과 데이터 경계에 코드 검증을 함께 둔다. 검증 범위와 실패 시 동작을 명확히 정하고, 위험한 tool에는 별도의 권한 확인을 적용한다.

### Tracing

Tracing은 실행 중 model 호출, tool 사용, handoff 같은 단계를 기록해 흐름을 살펴보는 기능이다. 예상과 다른 tool 선택이나 실패 지점을 찾을 때 유용하다. trace에 프롬프트·tool 입출력 등 민감한 정보가 포함될 수 있으므로, 데이터 취급 정책에 맞게 활성화하고 접근을 관리한다.

### Streaming

Streaming은 실행 이벤트를 생성되는 대로 받아 UI에 전달할 때 사용한다. 최종 결과만 보여주는 대신 텍스트나 tool 진행 상태를 점진적으로 표시할 수 있다. 이벤트를 화면에 표시할 때 중간 이벤트와 최종 답변을 구분한다.

## 권장하는 개발 순서

1. 에이전트가 해결할 한 가지 업무와 성공 기준을 정한다.
2. `tools` 없이 최소 에이전트를 실행하고 `instructions`를 다듬는다.
3. 읽기 전용 data tool부터 추가하고, 인수·오류·권한을 검증한다.
4. 실제 사용자 요청 사례로 결과를 평가한다.
5. 필요에 따라 구조화된 출력, guardrail, streaming, tracing을 더한다.
6. 단일 에이전트로 다루기 어려운 이유가 분명할 때 handoff나 agent-as-tool 패턴을 적용한다.

`model`은 처음부터 지나치게 작은 모델로 제한하기보다 업무 기준선을 먼저 확인한 뒤, 품질을 유지하면서 비용과 지연 시간을 줄일 수 있는지 평가한다. 운영 전에는 정상 사례뿐 아니라 불완전한 입력, tool 실패, 거부되어야 할 요청도 평가 사례에 포함한다.

## 직접 실행해보기

예제는 저장소 루트에서 실행한다. `requirements.txt`에 Agents SDK와 `python-dotenv`가 포함되어 있다. 가상 환경을 활성화한 뒤 의존성을 설치하고, 루트의 `.env`에 `OPENAI_API_KEY`를 설정한다.

```bash
pip install -r requirements.txt
cp .env.example .env
```

각 예제를 실행한다.

```bash
python script/agents_sdk.py
python script/agents_sdk_tools.py
python script/agents_sdk_structured_output.py
python script/agents_sdk_handoff.py
python script/agents_sdk_guardrails.py
```

| 파일 | 실습 내용 |
| --- | --- |
| [`agents_sdk.py`](../script/agents_sdk.py) | `Agent`를 만들고 `Runner`로 한 번 실행 |
| [`agents_sdk_tools.py`](../script/agents_sdk_tools.py) | `@function_tool` 함수와 `context` 전달 |
| [`agents_sdk_structured_output.py`](../script/agents_sdk_structured_output.py) | Pydantic model로 결과 형식 지정 |
| [`agents_sdk_handoff.py`](../script/agents_sdk_handoff.py) | 전문 에이전트로 handoff, agent-as-tool 호출 비교 |
| [`agents_sdk_guardrails.py`](../script/agents_sdk_guardrails.py) | 입력 guardrail tripwire로 요청 차단 |

예제는 `gpt-4.1-mini`를 사용한다. 다른 모델을 쓰려면 각 파일의 `model` 값을 바꾼다. `agents_sdk_guardrails.py`의 키워드 검사는 guardrail API 흐름을 보여주는 교육용 예시이며, 실제 민감정보 탐지 정책을 대신하지 않는다. SDK tracing은 기본 동작으로 실행 추적을 기록할 수 있으므로 민감한 입력으로 실습하지 않는다.

## 참고 자료

- 영상: [OpenAI Agents SDK 튜토리얼](https://www.youtube.com/watch?v=LmVUTbivKSg)
- 예제 코드 및 주제별 실습: [dabidstudio/openai-agents-sdk-tutorial](https://github.com/dabidstudio/openai-agents-sdk-tutorial)
- 실용적인 설계 가이드: [A practical guide to building agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
- 공식 SDK 문서: [OpenAI Agents SDK for Python](https://openai.github.io/openai-agents-python/) · [Quickstart](https://openai.github.io/openai-agents-python/quickstart/)
- 프로젝트의 관련 문서: [Function calling / tool calling](./function_calling.md) · [Responses API](./responses_api.md)

> 참고 범위: 영상의 YouTube 페이지에서 자막·전문을 직접 가져오지 못했다. 따라서 이 문서는 영상의 타임스탬프별 축어 요약이 아니라, 요청한 튜토리얼 저장소의 주제 구성과 OpenAI 실용 가이드에 맞춰 SDK 개념을 정리한 학습 문서다.

## Appendix

### 튜토리얼 저장소의 학습 경로

제공된 저장소는 아래 흐름으로 예제를 나눈다. 각 파일은 저장소에서 직접 확인할 수 있다.

| 단계 | 주제 | 예제 |
| --- | --- | --- |
| 1 | 기본 에이전트 | [`1_basic.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/1_basic.py) |
| 2 | 대화, 스트리밍, 채팅 UI | [`2_1_chat.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/2_1_chat.py), [`2_2_chat_stream.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/2_2_chat_stream.py), [`2_3_chat_ui.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/2_3_chat_ui.py) |
| 3 | 함수·내장 tool, MCP, agent-as-tool | [`3_1_tool.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/3_1_tool.py), [`3_2_tool_mcp.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/3_2_tool_mcp.py), [`3_3_tool_agent.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/3_3_tool_agent.py) |
| 4 | 구조화 출력, Context, Guardrail, Handoff | [`4_1_structured_output.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/4_1_structured_output.py), [`4_2_context.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/4_2_context.py), [`4_3_guardrail.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/4_3_guardrail.py), [`4_4_handoff.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/4_4_handoff.py) |
| 5 | 여행 일정 수립 에이전트 통합 | [`5_final_agent.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/5_final_agent.py) |
| 6 | 다른 모델 공급자 연동과 tracing | [`6_1_gemini.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/6_1_gemini.py), [`6_2_tracing.py`](https://github.com/dabidstudio/openai-agents-sdk-tutorial/blob/main/6_2_tracing.py) |

저장소 README의 실행 예시는 `uv add openai-agents streamlit python-dotenv`, `.env`에 `OPENAI_API_KEY` 설정, `uv run 1_basic.py` 실행 순서다. 외부 모델 공급자 연동은 별도 설정이 필요하므로 해당 예제의 최신 코드와 공식 SDK 문서를 확인한다.

### SDK와 직접 API 호출의 구분

이 저장소의 [Responses API 문서](./responses_api.md)와 [함수 호출 문서](./function_calling.md)는 OpenAI Python SDK의 `client.responses.create(...)`를 직접 호출하는 예시다. Agents SDK는 그보다 높은 수준에서 `Agent`와 `Runner`를 사용해 tool 실행 루프와 에이전트 협업을 구성한다. 둘 다 OpenAI model 및 tool 흐름을 다룰 수 있지만, 코드의 인터페이스와 추상화 수준은 다르다.

### 주요 개념을 실행 흐름으로 보기

```text
사용자 요청
    ↓
Runner가 Agent 실행
    ↓
model이 답변 또는 tool 사용을 선택
    ├─ tool 호출 → 검증 및 실행 → 결과를 model에 전달 ─┐
    ├─ handoff → 전문 Agent로 제어 전달 ───────────┤
    └─ 최종 출력 → 필요하면 구조화된 결과 반환       │
                   ↑───────────────────────────────┘
```

Guardrail은 입력·출력이나 tool 흐름을 검증하고, tracing은 실행 단계를 관찰할 수 있도록 기록한다. 두 기능은 에이전트의 실제 동작을 검증하고 디버깅하는 데 사용한다.
