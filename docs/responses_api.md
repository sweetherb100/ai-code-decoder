# OpenAI Responses API

> 목적: Responses API의 기본 요청 방식과 대화 상태, 도구, 구조화된 출력을 이해한다.

## 한 줄로 이해하기

> **Responses API는 하나의 인터페이스에서 텍스트 응답, 대화 맥락, 도구 호출, 구조화된 결과를 주고받는 API다.**

Responses API를 직접 호출할지 Agents SDK를 사용할지는 에이전트 실행 루프를 앱에서 직접 관리할지에 따라 결정한다. 짧은 요청·응답이나 직접 제어가 목적이면 Responses API를, 여러 turn의 tool 실행·handoff·guardrail을 SDK에 맡기려면 Agents SDK를 검토한다. 결정 기준과 예시는 [Responses API와 Agents SDK 비교](./agents_sdk.md#responses-api와-agents-sdk-중-선택하기)를 참고한다.

Chat Completions에서는 주로 `messages`를 보내고 `choices`의 메시지를 받는다. Responses API에서는 `input`을 보내고 텍스트, 함수 호출, 내장 도구 결과, 추론 항목 등이 포함될 수 있는 `output`을 받는다. 따라서 응답을 항상 단일 텍스트로 가정하지 않고 출력 항목의 종류를 살펴야 한다.

## 전체 흐름

```text
사용자 입력과 지침, 필요하면 도구 정의 전달
                    ↓
             responses.create(...)
                    ↓
         response.output 항목 확인
          ↙          ↓          ↘
      텍스트     도구 호출     구조화된 결과
                    ↓
           앱이 호출을 실행하고 결과 전달
                    ↓
       최종 답변 또는 다음 도구 호출
```

요청에 도구를 설정하면 모델이 그 도구를 사용할 수 있다. 도구의 종류에 따라 실행과 결과 전달을 앱이 맡거나 API가 맡으며, 두 흐름의 비교는 Appendix를 참고한다.

## 핵심 개념

| 개념 | 설명 |
| --- | --- |
| `input` | 문자열 또는 대화 항목으로 표현하는 입력 |
| `instructions` | 응답의 역할과 제약을 설명하는 지침 |
| `output` | 텍스트, 함수 호출 등 하나 이상의 응답 항목 |
| `output_text` | 텍스트 응답을 편리하게 읽는 SDK 속성 |
| `previous_response_id` | 앞선 응답을 지정해 대화 맥락을 이어가는 방법 |
| `tools` | 함수 도구나 웹 검색 같은 내장 도구 정의 |
| `text.format` | JSON Schema 기반 구조화된 텍스트 출력 형식 |

`output_text`는 텍스트를 간단히 꺼낼 때 유용하지만, 도구 호출을 처리하거나 모든 출력 유형을 구분해야 하는 코드에서는 `response.output`을 확인한다.

## 기본 텍스트 요청
`client.responses.create(...)`가 API 요청을 만들고, `response.output_text`가 사용자에게 보여줄 텍스트를 반환한다. API 키는 SDK가 기본 환경 변수 `OPENAI_API_KEY`에서 읽는다.

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-4.1-mini",
    instructions="간결하고 정확하게 답하세요.",
    input="Responses API를 한 문장으로 설명해줘.",
)

print(response.output_text)
```

## 대화 상태 이어가기

후속 요청에 `previous_response_id`를 전달하면 서버가 앞 응답과 연결해 대화 맥락을 이어갈 수 있다.

Responses API 응답은 기본적으로 저장되며, 공식 문서 기준 기본 보존 기간은 30일이다. 따라서 `previous_response_id`로 이어가려면 이전 응답이 저장되어 있고 참조 가능한 상태여야 한다. 응답 저장을 끄려면 `store=False`를 지정할 수 있지만, 이때는 저장된 응답 ID에 의존하지 말고 앱이 필요한 대화 항목을 보관해 다음 요청에 다시 보내는 상태 관리 방식을 사용한다. 자세한 내용은 [대화 상태 가이드](https://developers.openai.com/api/docs/guides/conversation-state)와 [데이터 제어 문서](https://developers.openai.com/api/docs/guides/your-data)를 참고한다.


```python
first = client.responses.create(
    model="gpt-4.1-mini",
    input="서울 여행 계획을 세워줘.",
)

follow_up = client.responses.create(
    model="gpt-4.1-mini",
    previous_response_id=first.id,
    input="대중교통 위주로 바꿔줘.",
)

print(follow_up.output_text)
```

다른 방법은 애플리케이션이 이전 대화의 메시지를 저장해뒀다가, 다음 요청의 `input`에 다시 넣는 것이다.

여기서 메시지는 앞서 보낸 **사용자 질문**과 그에 대한 **assistant 답변**을 말한다. 예를 들어 첫 요청에서 사용자가 "서울 여행 계획을 세워줘"라고 하고 assistant가 "3일 일정을 제안합니다"라고 답했다면, 다음 요청에는 그 두 메시지와 새 사용자 요청을 넣는다.

```python
response = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {"role": "user", "content": "서울 여행 계획을 세워줘."},
        {"role": "assistant", "content": "3일 일정을 제안합니다."},
        {"role": "user", "content": "대중교통 위주로 바꿔줘."},
    ],
)
```

## 함수 호출과 도구

Responses API는 사용자 정의 함수를 `tools`에 등록할 수 있다. 모델은 함수 호출 요청을 출력하고, 애플리케이션은 함수와 인수를 검증해 실행한 뒤 결과를 `function_call_output`으로 전달한다. 개념과 안전한 실행 패턴은 [function_calling.md](./function_calling.md)에 자세히 정리되어 있다.

그 밖에 API가 제공하는 도구도 요청에 포함할 수 있다.

- **Web search**: 최신 웹 정보를 찾을 때 사용한다.
- **File search**: 업로드 파일 또는 벡터 저장소의 정보를 찾을 때 사용한다.
- **Computer use**: 모델이 컴퓨터 인터페이스를 조작하는 작업 흐름에 사용한다.
- **Function calling**: 앱이 작성한 코드나 서비스와 모델을 연결한다.

도구별 지원 모델, 실행 방식, 요금 및 제한은 달라질 수 있으므로 실제 적용 때 공식 가이드를 확인한다.

## 구조화된 출력

응답을 JSON 형태로 받아 후속 코드에서 처리해야 한다면 구조화된 출력 형식을 지정할 수 있다. 이는 단순히 프롬프트에 “JSON으로 답하라”고 쓰는 것보다 결과 형식을 명시하는 방식이다.

```python
response = client.responses.create(
    model="gpt-4.1-mini",
    input="회의 메모를 요약하고 제목을 붙여줘: 이번 주 배포는 금요일로 미뤄졌고 QA가 필요하다.",
    text={
        "format": {
            "type": "json_schema",
            "name": "meeting_summary",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "action_items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "summary", "action_items"],
                "additionalProperties": False,
            },
        }
    },
)

print(response.output_text)
```

## 적용할 때 기억할 점

1. **응답은 여러 종류의 항목으로 구성될 수 있다.** 텍스트만 필요하면 `output_text`를 사용하고, 도구 실행이 있으면 `output`을 검사한다.
2. **함수 호출 요청과 함수 실행은 별개다.** 앱에서 등록된 함수인지, 인수가 유효한지, 사용자가 실행 권한이 있는지 확인한다.
3. **맥락 유지 방식을 명시적으로 선택한다.** `previous_response_id` 연결 또는 애플리케이션의 대화 이력 관리 중 앱 요구에 맞는 방식을 쓴다.
4. **후속 코드가 응답을 읽고 처리한다면 구조화된 출력을 지정한다.** `text.format`에 JSON Schema를 설정해 기대하는 필드와 형식을 명시하면, 단순히 프롬프트로 JSON을 요청하는 것보다 결과를 코드에서 다루기 쉽다.

## 참고 자료

- 영상: [OpenAI Just Changed Everything (Responses API Walkthrough)](https://www.youtube.com/watch?v=0pGxoubWI6s)
- 실습 코드와 주제 개요: [Dave Ebbelaar의 ai-cookbook `05-responses`](https://github.com/daveebbelaar/ai-cookbook/tree/main/models/openai/05-responses)
- OpenAI API 문서: [Responses API 가이드](https://developers.openai.com/api/docs/guides/text) · [API 참조](https://developers.openai.com/api/reference/resources/responses/methods/create)
- 관련 문서: [Function calling / tool calling](./function_calling.md)

## Appendix

### 1. `response.output`의 항목 타입

각 `response.output` 항목은 `type` 필드로 구분한다. 대표 타입과 기본 처리 방법은 다음과 같다. 실제로 반환되는 항목은 요청에 설정한 도구와 모델의 지원 기능에 따라 달라진다.

| `type` | 의미 | 애플리케이션에서의 처리 |
| --- | --- | --- |
| `message` | assistant 메시지. `content` 안에 `output_text`, `refusal`, 이미지 등의 콘텐츠가 있을 수 있다. | `content` 항목의 타입도 확인한다. 사용자에게 보여줄 텍스트는 `output_text`에서 읽는다. |
| `function_call` | 애플리케이션이 정의한 함수 호출 요청. 보통 `name`, `arguments`, `call_id`를 포함한다. | 이름과 인수를 검증하고 앱에서 함수를 실행한 뒤, 결과를 후속 입력의 `function_call_output`으로 전달한다. |
| `reasoning` | 추론 모델의 추론 관련 항목 또는 요약. | 일반 사용자에게 표시하는 답변으로 취급하지 않는다. 필요하면 대화 연속성 용도로 공식 지침을 따른다. |
| `web_search_call` | 내장 웹 검색 도구가 수행한 검색 작업과 상태/행동 정보. | 검색 호출 상태와 필요한 출처 정보를 확인한다. 사용자에게 보여줄 최종 답은 보통 별도의 `message`에 있다. |
| `file_search_call` | 내장 파일 검색 도구의 호출 정보. | 호출 상태를 확인한다. 결과 상세는 요청에서 지원되는 `include` 옵션을 지정해야 포함될 수 있다. |
| `computer_call` | 컴퓨터 사용 도구에 대한 동작 요청. | 명세된 동작을 컴퓨터 사용 흐름에 연결하고 결과를 후속 입력으로 돌려준다. |
| `code_interpreter_call` | 코드 인터프리터 도구 실행 정보. | 실행 상태와 출력을 도구 흐름에 맞춰 처리한다. |
| `image_generation_call` | 이미지 생성 도구 실행 정보. | 생성 상태 및 완료된 이미지 결과를 처리한다. |
| `local_shell_call` 또는 `shell_call` | 지원되는 환경에서 셸 실행을 요청하는 항목. | 허용된 실행 환경과 도구 흐름에 따라 요청을 처리한다. 지원 여부는 모델/API 환경에 따라 다르다. |
| `mcp_list_tools` 또는 `mcp_call` | MCP 서버의 도구 목록 조회 또는 도구 호출 항목. | MCP 연결 및 반환 상태/결과를 처리한다. |

여기서 `function_call_output`은 모델이 함수를 호출하라는 응답 항목이 아니라, **앱이 실행한 함수의 결과를 API에 돌려줄 때 사용하는 입력 항목**이다.

### 2. 사용자 정의 함수와 내장 도구 비교

요청의 `tools`에는 모델이 사용할 수 있는 도구와 사용 방법을 알려준다. 사용자 정의 함수의 경우 이 설명만 전달하며, 앱의 함수 코드를 OpenAI에 보내거나 실행시키는 것은 아니다. 반면 웹 검색과 파일 검색은 OpenAI가 제공하는 도구이며, 앱은 요청에서 도구를 설정해 사용한다.

| 구분 | 사용자 정의 함수 도구 | 내장 도구 (예: 웹 검색, 파일 검색) |
| --- | --- | --- |
| 도구 정의 | 앱이 함수 이름과 입력 형식 등을 요청에 등록 | 앱이 API가 제공하는 도구와 필요한 설정을 요청에 지정 |
| 실행 주체 | 애플리케이션 | OpenAI API |
| 모델의 응답/처리 | 모델이 `function_call`로 함수명과 인수를 반환하고, 앱이 검증·실행한 뒤 결과를 `function_call_output`으로 전달 | 모델이 도구를 사용하면 API가 실행하고 결과를 모델에 연결 |
| 예 | `get_order_status(order_id)` 요청을 받고 앱 코드가 주문 데이터베이스 조회 | API가 웹을 검색하거나 설정된 파일을 검색 |

흐름을 비교하면 다음과 같다.

```text
사용자 정의 함수: 앱이 함수 설명 등록 → 모델이 호출 요청 → 앱 코드가 실행 → 앱이 결과 전달 → 모델 답변
내장 도구:       앱이 도구 사용 설정   → 모델이 사용 결정 → API가 실행       → API가 결과 연결 → 모델 답변
```

둘 다 모델에게 도구 사용 방법을 알려주지만, 사용자 정의 함수는 **앱이 실행**하고 내장 도구는 **API가 실행**한다. 함수 호출을 처리하는 구체적인 코드 패턴은 [function_calling.md](./function_calling.md)에 정리되어 있다.
