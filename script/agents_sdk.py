"""Agents SDK의 최소 구성: Agent와 Runner를 실행한다."""

from pathlib import Path

from agents import Agent, Runner
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    agent = Agent(
        name="역사 튜터",
        instructions="역사 질문에 명확하고 간결하게 답하세요.",
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(agent, "로마 제국은 언제 멸망했나요?")
    print(result.final_output)


if __name__ == "__main__":
    main()
