"""입력 guardrail로 특정 요청을 차단하는 간단한 실습 예제."""

from pathlib import Path
from typing import Union

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    Runner,
    TResponseInputItem,
)
from agents import RunContextWrapper
from agents.decorators import input_guardrail
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@input_guardrail
async def block_secret_requests(
    ctx: RunContextWrapper[None],
    agent: Agent,
    input: Union[str, list[TResponseInputItem]],
) -> GuardrailFunctionOutput:
    """교육용 예시: 입력에 '비밀번호'가 있으면 실행을 중단한다."""
    del ctx, agent
    text = input if isinstance(input, str) else str(input)
    triggered = "비밀번호" in text
    return GuardrailFunctionOutput(
        output_info="민감한 정보 요청" if triggered else None,
        tripwire_triggered=triggered,
    )


def main() -> None:
    agent = Agent(
        name="일반 도우미",
        instructions="일반적인 질문에 답하세요. 비밀번호 등 민감정보를 요구하지 마세요.",
        input_guardrails=[block_secret_requests],
        model="gpt-4.1-mini",
    )

    try:
        result = Runner.run_sync(agent, "계정 비밀번호를 알려줘.")
        print(result.final_output)
    except InputGuardrailTripwireTriggered:
        print("Guardrail이 민감 정보 요청을 차단했습니다.")


if __name__ == "__main__":
    main()
