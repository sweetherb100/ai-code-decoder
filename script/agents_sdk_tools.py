"""고정된 사실을 돌려주는 함수 tool의 기본 예제."""

from pathlib import Path

from agents import Agent, Runner, function_tool
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@function_tool
def history_fun_fact() -> str:
    """짧은 역사 사실 하나를 반환한다."""
    return "상어는 나무보다 먼저 지구에 나타났습니다."


def main() -> None:
    agent = Agent(
        name="역사 튜터",
        instructions="역사 질문에 답하세요. 도움이 되면 history_fun_fact 도구를 사용하세요.",
        tools=[history_fun_fact],
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(agent, "고대 생명에 관해 놀라운 사실 하나 알려줘.")
    print(result.final_output)


if __name__ == "__main__":
    main()
