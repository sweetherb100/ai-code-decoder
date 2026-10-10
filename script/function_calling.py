import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load the .env file from the repository root when this script runs directly.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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
    },
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

    while True:
        calls = [item for item in response.output if item.type == "function_call"]
        # 모델이 최종 답변을 반환해 함수 호출이 없으면 답변을 돌려주고 반복을 끝낸다.
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
