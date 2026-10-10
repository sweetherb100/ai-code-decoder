# Function calling / tool calling

> 목적: 모델이 애플리케이션에 등록된 함수를 선택하고 실행 결과를 활용하도록 연결하는 기본 패턴을 익힌다.
>
> 예제는 Python OpenAI SDK의 **Responses API**를 기준으로 한다. 영상의 function calling 개념은 참고하되, 영상에 나온 구형 `functions` / `function_call` 인자는 현재 예제의 `tools` / `tool_choice`로 옮겼다.

## 한 줄로 이해하기

> **AI가 “이 함수를 이 값으로 실행해 주세요”라고 우리 프로그램에 요청하면, 우리 프로그램이 확인하고 함수를 실행한 뒤 결과를 AI에게 알려준다.**

### 항공편 조회를 순서대로 보면

1. 사용자가 “암스테르담에서 뉴욕 가는 항공편을 알려줘”라고 앱에 입력한다.
2. 앱은 질문과 함께 “`get_flight_info`라는 함수가 있고 출발지·도착지를 받는다”는 설명을 모델에 보낸다.
3. 모델은 답변 대신 함수 호출 요청을 돌려줄 수 있다. 예: `get_flight_info`, 출발지 `AMS`, 도착지 `JFK`.
4. 앱이 요청을 확인하고 자기 안에 작성해 둔 `get_flight_info` Python 코드를 실행한다.
5. 함수가 항공편 정보를 돌려주면, 앱은 그 결과를 모델에 다시 보낸다.
6. 모델은 받은 결과를 문장으로 만들어 사용자에게 답한다.

보통 모델을 **두 번 호출**한다. 첫 번째 호출은 “어떤 함수를 어떤 값으로 실행할지” 정하고, 두 번째 호출은 함수 결과를 바탕으로 사용자에게 답한다. 같은 모델을 두 번 요청하는 것이지, AI가 두 개 필요한 것은 아니다. 도구가 필요 없는 질문이면 한 번만 호출할 수 있고, 여러 도구를 차례로 써야 하면 두 번보다 더 호출할 수 있다.

그래서 function calling은 **AI가 우리 코드를 직접 실행하는 기능**이라기보다, AI가 필요한 함수를 골라 실행 요청을 만들고 우리 앱이 그 요청을 처리하는 연결 방식이다.

**요청과 실행은 다른 단계다.** 모델이 함수 호출 요청을 만들어도 Python 코드는 아직 실행되지 않았다. 앱이 요청을 받아 허용된 함수인지 확인하고 코드를 실행해야 실제 결과가 나온다.

## 전체 흐름

```text
사용자 요청
    ↓
모델에 사용 가능한 도구와 JSON Schema 전달
    ↓
모델이 함수 이름과 인수를 반환
    ↓
애플리케이션이 함수·인수를 검증하고 실행
    ↓
실행 결과를 같은 호출 ID로 모델에 전달
    ↓
모델이 최종 답변 또는 다음 도구 호출 반환
```

이 과정은 여러 차례 반복될 수 있다. 모델은 함수 설명을 보고 호출을 선택할 뿐, 애플리케이션의 Python 코드나 데이터베이스를 직접 읽고 실행하지 않는다. 함수는 외부 연동일 필요가 없으며, 앱이 의도적으로 공개한 내부 함수도 같은 방식으로 연결한다. [OpenAI Function Calling 가이드](https://developers.openai.com/api/docs/guides/function-calling)

## 영상의 인자와 Responses API 인자 대응

영상은 구형 Chat Completions 문법을 사용한다. 현재 예제는 Responses API 문법을 사용하므로 인자 이름과 응답 구조가 다르다.

| 역할 | 영상의 구형 문법 | Responses API 예제 |
| --- | --- | --- |
| 사용할 함수 스키마 등록 | `functions=[...]` | `tools=[{"type": "function", "name": ..., "parameters": ...}]` |
| 모델의 함수 선택 방식 | `function_call="auto"` | `tool_choice="auto"` (기본 동작) |
| 모델이 반환한 호출 | `message.function_call` | `response.output` 안의 `function_call` 항목 |
| 함수 실행 결과 전달 | `role="function"`, 함수 이름 | `type="function_call_output"`, `call_id` |

`tools`는 모델이 사용할 수 있는 함수와 스키마를 등록하고, `tool_choice`는 이번 요청에서 도구를 선택하는 규칙을 정한다. 예를 들어 기본 `auto`는 호출 여부를 모델이 정하고, `required`는 하나 이상의 도구 호출을 요구한다. 특정 함수만 강제하는 설정도 있다. 호출 결과를 나타내는 응답 항목의 타입 이름은 `function_call`이므로, 이것을 요청 인자였던 구형 `function_call`과 혼동하지 않는다. [OpenAI 도구 선택 문서](https://developers.openai.com/api/docs/guides/function-calling)

## 작은 실행 예제

### 1. 함수와 도구 스키마 정의

도구 스키마는 모델이 어떤 함수가 있는지, 어떤 인수를 받아야 하는지 알려준다.

함수 설명은 호출 선택에 영향을 준다. 함수 이름은 구체적으로 짓고, 설명에는 **무엇을 하는지**, 인수 설명에는 **허용되는 값과 형식**을 적는다. 반환값이 있다는 점도 모델이 다음 단계에서 이해할 수 있도록 명시한다.

```python
import json
from openai import OpenAI

client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "name": "get_flight_info",
        "description": "두 공항 코드 사이의 예정 항공편 정보를 조회한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "출발 공항의 IATA 코드. 예: AMS",
                },
                "destination": {
                    "type": "string",
                    "description": "도착 공항의 IATA 코드. 예: JFK",
                },
            },
            "required": ["origin", "destination"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


def get_flight_info(origin: str, destination: str) -> dict:
    """예제를 위한 모의 조회 함수. 실제 앱에서는 항공 API/DB를 호출한다."""
    flights = {
        ("AMS", "JFK"): {
            "flight_number": "KL643",
            "airline": "KLM",
            "departure": "2026-10-11T18:25:00+02:00",
        }
    }
    result = flights.get((origin.upper(), destination.upper()))
    if result is None:
        return {"found": False, "message": "해당 경로의 항공편을 찾지 못했습니다."}
    return {"found": True, **result}
```

### 2. 모델 호출, 실행, 결과 전달

```python
FUNCTIONS = {
    "get_flight_info": get_flight_info,
}


def ask_about_flight(question: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        instructions=(
            "항공편 조회가 필요하면 도구를 사용하세요. "
            "도구 결과에 없는 항공편 정보는 추측하지 마세요."
        ),
        input=question,
        tools=TOOLS,
        tool_choice="auto",
    )

    # 응답에 함수 호출이 있을 수 있다. 도구 실행은 우리 애플리케이션의 책임이다.
    while True:
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return response.output_text

        tool_outputs = []
        for call in calls:
            function = FUNCTIONS.get(call.name)
            if function is None:
                result = {"error": f"허용되지 않은 함수: {call.name}"}
            else:
                try:
                    arguments = json.loads(call.arguments)
                    # JSON Schema 검증과 별개로, 업무 규칙·권한을 여기서 검증한다.
                    origin = arguments["origin"]
                    destination = arguments["destination"]
                    if not isinstance(origin, str) or not isinstance(destination, str):
                        raise ValueError("출발지와 도착지는 문자열이어야 합니다.")
                    origin = origin.upper()
                    destination = destination.upper()
                    if len(origin) != 3 or len(destination) != 3:
                        raise ValueError("공항 코드는 IATA 3자리여야 합니다.")
                    result = function(origin=origin, destination=destination)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    result = {"error": str(exc)}

            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

        # 이전 응답과 도구 결과를 연결해 모델이 최종 답변/다음 호출을 하도록 한다.
        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=(
                "도구 결과에 근거해 답하세요. 결과에 없는 항공편 정보는 추측하지 마세요."
            ),
            previous_response_id=response.id,
            input=tool_outputs,
            tools=TOOLS,
            tool_choice="auto",
        )


print(ask_about_flight("암스테르담에서 뉴욕으로 가는 항공편 정보를 알려줘."))
```

여기서 `call_id`는 함수 호출과 결과를 짝짓는 값이다. 응답에 여러 함수 호출이 올 수 있으므로 모든 `function_call` 항목을 처리한다. 예제의 `previous_response_id`는 앞선 응답을 이어가는 방법이다. 대화 전체를 직접 보관하는 설계라면 이전 모델 출력과 도구 결과를 입력에 누적해 전달할 수도 있다. [Responses API 도구 호출 예제](https://developers.openai.com/api/docs/guides/function-calling)

## 영상 예제에서 배울 점

영상의 공항 에이전트는 항공편 조회, 예약, 불만 접수 도구를 등록하고 모델이 요청에 맞는 함수를 선택하는 것을 보여준다. 핵심은 자연어를 제어 가능한 인수로 바꾸고, 앱의 실제 함수를 실행한 뒤, 결과로 답변을 만드는 구조다.

마지막 복합 요청에서는 예약 함수에 필요한 항공편 시간과 항공사가 실제 조회 결과에서 오지 않았는데도 모델이 값을 채운다. 함수 스키마에서 필수라고 표시하는 것은 **입력이 있어야 한다**는 뜻이지, 그 값이 실제 사실이라는 보증이 아니다. 실전에서는 다음처럼 처리한다.

1. 예약 전에 조회 도구를 실행해 실제 항공편을 찾는다.
2. 예약 함수는 모델이 만든 날짜·항공사 문자열을 그대로 신뢰하지 않고, 조회된 항공편 ID를 받도록 설계한다.
3. 사용자가 고른 항공편과 예약 조건을 서버에서 다시 확인한다.
4. 예약이나 결제처럼 변경을 일으키는 작업은 별도의 사용자 확인과 권한 검사를 거친다.

## 참고 자료

- 영상: [OpenAI Function Calling - Full Beginner Tutorial](https://www.youtube.com/watch?v=aqdWSYWC_LI)
- 원본 실습 코드: [openai_function_calling.py](https://github.com/daveebbelaar/langchain-experiments/blob/main/openai-functions/openai_function_calling.py)
- 현재 API 개념 및 예제: [OpenAI Function Calling 가이드](https://developers.openai.com/api/docs/guides/function-calling)

영상의 원본 코드는 초기 `functions` / `function_call` 파라미터와 LangChain 래퍼를 보여준다. 이 문서의 코드는 같은 개념을 Responses API의 `tools` / `tool_choice`와 `function_call_output` 구조로 다시 구성했으며, 최신 모델명·SDK 지원 여부는 실행 시 공식 API 문서를 확인한다.

원본 코드에는 모델이 반환한 함수 이름을 `eval()`로 실행하는 부분이 있다. 모델 출력 문자열을 코드로 실행하는 패턴은 권한 경계를 무너뜨릴 수 있으므로 사용하지 않는다. 위 예제처럼 고정된 함수 매핑에서만 선택하고, 함수 인수도 검증한다.


## 용어: function calling과 tool calling

OpenAI 문서에서는 **function calling을 tool calling이라고도 부른다**. 함수는 도구의 한 종류이며, function tool은 JSON Schema로 함수 이름과 인수를 정의하는 형태다. 다만 `tool`은 더 넓은 개념이다. 웹 검색, 코드 실행, MCP 연결 등 함수 형태가 아닌 도구도 포함하므로, 모든 tool calling이 사용자 정의 함수 호출만을 뜻하지는 않는다. 대화에서는 두 용어가 같은 기능을 가리키는 문맥도 흔하다. [OpenAI 용어와 흐름](https://developers.openai.com/api/docs/guides/function-calling)


## Appendix: Python OpenAI SDK, Responses API, Agents SDK

이 문서의 예제를 이해할 때는 **SDK**와 **API**를 구분하면 된다.

- **OpenAI Python SDK**는 Python 프로그램에서 OpenAI API를 호출하는 라이브러리다. 예제의 `OpenAI()`와 `client.responses.create(...)`가 여기에 해당한다.
- **Responses API**는 SDK가 요청을 보내는 서버 측 API 인터페이스다. Python SDK에서는 `client.responses.create(...)`로 호출한다.
- **OpenAI Agents SDK**는 에이전트, 도구, 실행·handoff 흐름 같은 상위 수준 구성을 제공하는 별도 Python 패키지다. 모델 호출과 도구 실행을 더 큰 에이전트 흐름 안에서 조율할 수 있다.
- **Agents API**는 또 다른 서버 측 API다. OpenAI가 관리하는 Codex harness에서 세션과 에이전트 실행을 운영한다. Python SDK에는 이를 호출하는 API namespace도 있으므로, "Agents API"가 보이면 Agents SDK의 별칭이라고 단정하지 말고 문맥을 확인한다.

따라서 이 문서의 코드는 **OpenAI Python SDK를 사용해 Responses API를 직접 호출하는 예제**이며, Agents SDK 예제가 아니다. Agents SDK도 OpenAI 모델을 사용할 때 기본적으로 Responses API를 사용하지만, `Agent`와 `Runner`가 도구 호출·턴 진행 같은 에이전트 실행 루프를 관리한다. 같은 Python SDK로 Chat Completions나 Agents API도 호출할 수 있다. 프로젝트 자체는 Agents SDK를 사용하므로, 프로젝트 코드의 `Agent` 구성과 이 문서의 `client.responses.create(...)` 예제는 서로 다른 계층의 사용 방식이다. [API 실행 방식 비교](https://developers.openai.com/api/docs/guides/agents) · [Agents SDK와 Responses API](https://openai.github.io/openai-agents-python/agents/) · [Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview) · [OpenAI Python SDK](https://github.com/openai/openai-python) · [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
