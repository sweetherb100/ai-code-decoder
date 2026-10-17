# OpenAI Agents SDK

> 목적: OpenAI Agents SDK의 기본 구성 요소와 에이전트 실행 흐름을 이해하고, tool·handoff·guardrail·tracing 기능을 어떤 상황에 적용할지 익힌다.

## 한 줄로 이해하기

> **Agents SDK는 에이전트의 실행 루프와 여러 에이전트 간 협업을 구성하는 Python 프레임워크다.**

일반적인 단일 LLM 요청은 입력에 대한 답을 한 번 생성한다. 에이전트는 작업을 진행하며 tool을 선택하고, 결과를 반영해 다음 단계를 수행한 뒤 종료 조건에 도달하면 결과를 반환한다. SDK의 `Runner`가 이 실행 루프를 관리한다.

## model, instructions, tools

OpenAI의 실용 가이드는 `model`, `tools`, `instructions` 세 가지를 에이전트의 기본 구성 요소로 설명한다. 에이전트를 구분하는 핵심은 model이 workflow 진행을 판단하고, 필요하면 tools를 선택해 작업을 이어가는 실행 흐름이다. Responses API는 그 요청과 응답을 직접 다루는 인터페이스이고, Agents SDK는 `Runner`가 tool 실행과 후속 turn을 관리하도록 돕는다.

| 공식 용어 | 역할 | 예시 |
| --- | --- | --- |
| `model` | 응답을 생성하고, 에이전트 흐름에서는 다음 행동을 판단 | 질문에 답하거나 tool 선택 |
| `tools` | 외부 데이터 조회 또는 작업 수행 | 함수, 웹 검색, MCP 서버 |
| `instructions` | 에이전트의 역할·절차·제약을 정의 | 모르는 정보는 추측하지 않기 |

## 기본 실행

다음은 SDK의 최소 형태를 보여주는 예시다. SDK 설치와 API 키 설정은 [공식 Quickstart](https://openai.github.io/openai-agents-python/quickstart/)을 따른다.

```python
from agents import Agent, Runner

agent = Agent(
    name="역사 튜터",
    instructions="역사 질문에 명확하고 간결하게 답하세요.",
)

result = Runner.run_sync(agent, "로마 제국은 언제 멸망했나요?")
print(result.final_output)
```

`Agent`는 `instructions`, `model`, `tools` 등을 정의한다. `Runner.run_sync`는 동기 실행 예시이며, 비동기 애플리케이션에서는 `Runner.run`을 사용할 수 있다. `Runner`는 model 응답이 tool 호출이면 tool 실행과 후속 model 호출을 이어가고, 최종 결과가 나오면 `final_output`에 제공한다.

## tools와 실행 흐름

`tools`는 에이전트가 현재 대화 바깥의 정보나 기능을 이용하게 한다. 함수 tool은 Python 함수로 정의하고, 웹 검색이나 MCP 같은 tool과 함께 에이전트에 제공할 수 있다.

```python
from agents import Agent, Runner, function_tool


@function_tool
def history_fun_fact() -> str:
    """짧은 역사 사실 하나를 반환한다."""
    return "상어는 나무보다 먼저 지구에 나타났습니다."


agent = Agent(
    name="역사 튜터",
    instructions="역사 질문에 답하세요. 도움이 되면 history_fun_fact 도구를 사용하세요.",
    tools=[history_fun_fact],
)

result = Runner.run_sync(agent, "고대 생명에 관해 놀라운 사실 하나 알려줘.")
print(result.final_output)
```

`@function_tool`은 Python 함수를 tool로 등록한다. model은 `instructions`와 함수 설명을 참고해 호출 여부를 선택하고, `Runner`가 함수를 실행해 결과를 model에 돌려준다.

Python 함수 외에도 SDK에서 다음 tool 유형을 사용할 수 있다.

| tool 유형 | 어디서 정의·실행되는가 | 실습 |
| --- | --- | --- |
| 함수 tool (`@function_tool`) | Python 함수로 정의하고 앱의 프로세스에서 실행 | [`agents_sdk_tool_function.py`](../script/agents_sdk_tool_function.py) |
| 웹 검색 (`WebSearchTool`) | OpenAI가 호스팅하며 검색 실행 | [`agents_sdk_tool_web_search.py`](../script/agents_sdk_tool_web_search.py) |
| MCP server | MCP server가 제공하는 tool을 연결해 사용 | [`agents_sdk_tool_mcp.py`](../script/agents_sdk_tool_mcp.py) |
| Agent as a tool | 직접 만든 specialist Agent를 다른 Agent의 tool로 등록 | [`agents_sdk_tool_agent.py`](../script/agents_sdk_tool_agent.py) |

직접 만든 Agent도 `specialist_agent.as_tool(...)`로 tool처럼 등록할 수 있다. 이 방식에서는 manager Agent가 specialist를 호출해 결과를 받은 뒤, 최종 답변의 흐름을 계속 관리한다. handoff는 specialist가 대화의 제어권을 이어받는 방식이다. 두 패턴의 코드 비교는 [`agents_sdk_handoff.py`](../script/agents_sdk_handoff.py)와 [`agents_sdk_tool_agent.py`](../script/agents_sdk_tool_agent.py)를 참고한다.

MCP 예제는 카페 메뉴가 적힌 `script/samples/cafe_menu.md`를 읽어 음료를 추천한다. `npx`가 filesystem MCP server를 실행하며, 이 server는 전달된 `script/samples` 폴더 안의 파일 도구를 에이전트에 제공한다. 실행 환경에 **Python 3.10 이상과 Node.js/npm**이 필요하다. `requirements.txt`는 Python 3.10 이상에서 MCP SDK를 설치한다. Python 3.9 환경에서는 이 예제를 실행할 수 없다. Python 3.10은 2026년 10월 지원이 종료됐으므로, 새 환경은 지원 중인 Python 3.12 이상을 권장한다. 최초 실행 시 npx가 MCP server 패키지를 가져온다. 이처럼 앱별 연결부를 직접 작성하는 대신 MCP server가 제공하는 tool을 SDK에 연결해 사용할 수 있다.

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

예제는 저장소 루트에서 실행한다. MCP 실습을 포함하려면 Python 3.12를 설치한 후, 저장소 루트에서 기존 가상환경을 새로 만든다. 아래 `rm -rf .venv` 명령은 저장소 루트의 `.venv`만 지운다. 가상환경에 필요한 패키지나 다른 파일을 보관한 적이 있다면 먼저 별도로 옮긴다.

```bash
python3.12 --version
deactivate  # 기존 가상환경이 활성화된 경우
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

`requirements.txt`에는 Agents SDK, `python-dotenv`와 MCP SDK가 포함되어 있다. 루트의 `.env`에 `OPENAI_API_KEY`를 설정한다.

각 예제를 실행한다.

```bash
python script/agents_sdk.py
python script/agents_sdk_tool_function.py
python script/agents_sdk_tool_web_search.py
python script/agents_sdk_tool_mcp.py
python script/agents_sdk_tool_agent.py
python script/agents_sdk_structured_output.py
python script/agents_sdk_handoff.py
python script/agents_sdk_guardrails.py
```

| 파일 | 실습 내용 |
| --- | --- |
| [`agents_sdk.py`](../script/agents_sdk.py) | `Agent`를 만들고 `Runner`로 한 번 실행 |
| [`agents_sdk_tool_function.py`](../script/agents_sdk_tool_function.py) | `@function_tool`로 간단한 Python 함수를 tool로 등록 |
| [`agents_sdk_tool_web_search.py`](../script/agents_sdk_tool_web_search.py) | OpenAI hosted Web Search tool 사용 |
| [`agents_sdk_tool_mcp.py`](../script/agents_sdk_tool_mcp.py) | MCP가 카페 메뉴 파일을 읽고, 조건에 맞는 음료를 추천. Node.js/npm 필요 |
| [`agents_sdk_tool_agent.py`](../script/agents_sdk_tool_agent.py) | 직접 만든 Agent를 specialist tool로 사용 |
| [`agents_sdk_structured_output.py`](../script/agents_sdk_structured_output.py) | Pydantic model로 결과 형식 지정 |
| [`agents_sdk_handoff.py`](../script/agents_sdk_handoff.py) | 전문 에이전트로 handoff, agent-as-tool 호출 비교 |
| [`agents_sdk_guardrails.py`](../script/agents_sdk_guardrails.py) | 입력 guardrail tripwire로 요청 차단 |

예제는 `gpt-4.1-mini`를 사용한다. 다른 모델을 쓰려면 각 파일의 `model` 값을 바꾼다. `agents_sdk_guardrails.py`의 키워드 검사는 guardrail API 흐름을 보여주는 교육용 예시이며, 실제 민감정보 탐지 정책을 대신하지 않는다. SDK tracing은 기본 동작으로 실행 추적을 기록할 수 있으므로 민감한 입력으로 실습하지 않는다.

## 참고 자료

- 영상: [OpenAI Agents SDK 튜토리얼](https://www.youtube.com/watch?v=LmVUTbivKSg)
- 예제 코드 및 주제별 실습: [dabidstudio/openai-agents-sdk-tutorial](https://github.com/dabidstudio/openai-agents-sdk-tutorial)
- 실용적인 설계 가이드: [A practical guide to building agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)
- 공식 SDK 문서: [OpenAI Agents SDK for Python](https://openai.github.io/openai-agents-python/) · [Quickstart](https://openai.github.io/openai-agents-python/quickstart/)
- 공식 tool 가이드: [Tools](https://openai.github.io/openai-agents-python/tools/) · [MCP](https://openai.github.io/openai-agents-python/mcp/)
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

### Responses API와 Agents SDK 중 선택하기

두 선택지는 같은 일을 하는 서로 다른 model이 아니다. **Responses API는 model 요청과 응답을 직접 다루는 API이고, Agents SDK는 에이전트 실행을 관리하는 런타임이다.** Agents SDK는 OpenAI model을 사용할 때 기본적으로 Responses API를 호출하면서, 그 위에서 turn 진행과 tool 실행 같은 흐름을 관리한다.

| 판단 기준 | Responses API 직접 호출 | Agents SDK |
| --- | --- | --- |
| 적합한 흐름 | 한 번의 요청·응답, 또는 앱이 명시적으로 관리하는 짧은 흐름 | tool 호출과 후속 응답이 이어지는 에이전트 실행 루프 |
| 실행 루프 | 앱이 다음 API 호출, tool 실행, 종료 시점을 정함 | `Runner`가 응답에 따라 tool 실행과 다음 turn을 진행 |
| tool 처리 | API가 제공하는 hosted tool은 설정에 따라 API가 실행. 사용자 정의 function은 앱이 실행·결과 전달 | SDK가 등록된 function tool 실행과 결과 연결을 관리 |
| 상태와 대화 | `input`, `previous_response_id` 또는 앱이 보관한 이력으로 직접 관리 | `Runner` 실행, `context`, 필요하면 `Session`으로 관리 |
| 여러 에이전트 | handoff나 에이전트 조율을 직접 구현 | handoff와 agent-as-tool 기능을 제공 |
| 선택 이유 | 흐름을 직접 제어하고 싶거나, 단일 호출·간단한 연동이 목적 | guardrail, handoff, session, tool loop 등 에이전트 기능을 활용하고 싶음 |

**결정적인 일반 작업은 Responses API를 고르는 근거가 되지 않는다.** 입력을 규칙대로 변환하는 것만 필요하면 일반 코드가 더 간단하다. 텍스트 해석이나 생성은 필요하지만 호출 흐름이 한 번으로 충분하면 Responses API를 고려한다. model이 tool을 고르고 결과를 읽은 뒤 다음 행동을 이어가야 하면 Agents SDK가 편리하다.

빠른 판단은 다음 질문으로 할 수 있다.

1. LLM이 필요한가? 필요하지 않다면 일반 코드나 규칙 기반 자동화를 사용한다.
2. LLM이 필요하다면, 앱이 요청·tool·상태·반복을 직접 제어해야 하는가? 그렇다면 Responses API를 직접 호출한다.
3. tool 사용과 여러 turn의 실행 루프를 SDK에 맡기거나 handoff·guardrail·session 기능이 필요한가? 그렇다면 Agents SDK를 사용한다.

두 방식을 한 제품에서 함께 사용해도 된다. 예를 들어 대화형 에이전트 흐름은 Agents SDK로 관리하고, 별도의 단순 분류나 한 번의 요약 요청은 Responses API로 처리할 수 있다.

| 예시 작업 | 시작점 |
| --- | --- |
| 입력 형식 검사, 정해진 규칙에 따른 값 변환 | 일반 Python 코드 |
| 회의록을 한 번 요약하거나 항목을 JSON으로 추출 | Responses API |
| 모델이 사내 조회 함수를 선택해 실행하고 결과를 바탕으로 답변 | Responses API 또는 Agents SDK. 앱이 루프를 직접 소유하면 전자, SDK 실행 루프를 맡기면 후자 |
| 접수 agent가 요청을 분류해 전문 agent로 넘김 | Agents SDK |

자세한 내용은 [Responses API 문서](./responses_api.md)와 본문의 [직접 실행해보기](#직접-실행해보기)를 참고한다. 공식 비교는 [Agents SDK 소개의 Responses API 비교](https://openai.github.io/openai-agents-python/#agents-sdk-or-responses-api)를 참고한다.
