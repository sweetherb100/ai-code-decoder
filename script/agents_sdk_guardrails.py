"""입력에 '비밀번호'가 있으면 Agent 실행을 막는 guardrail 예제."""

from pathlib import Path

from agents import Agent, GuardrailFunctionOutput, InputGuardrailTripwireTriggered, Runner
from agents.decorators import input_guardrail
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@input_guardrail
async def block_password_request(_ctx, _agent, input) -> GuardrailFunctionOutput:
    """사용자 입력에 '비밀번호'가 있는지 확인한다."""
    # guardrail에 전달된 사용자 입력을 간단한 문자열로 확인한다.
    contains_password = "비밀번호" in str(input)

    # tripwire_triggered가 True면 Runner가 실행을 중단한다.
    return GuardrailFunctionOutput(
        output_info="비밀번호 관련 요청은 처리하지 않습니다." if contains_password else None,
        tripwire_triggered=contains_password,
    )


def main() -> None:
    agent = Agent(
        name="일반 도우미",
        instructions="일반적인 질문에 답하세요.",
        input_guardrails=[block_password_request],
        model="gpt-4.1-mini",
    )

    try:
        result = Runner.run_sync(agent, "계정 비밀번호를 알려줘.")
        print(result.final_output)
    except InputGuardrailTripwireTriggered as exc:
        # 예외에 guardrail 결과가 포함되어 있어 output_info를 출력할 수 있다.
        print(exc.guardrail_result.output.output_info)


if __name__ == "__main__":
    main()
