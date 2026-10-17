"""Agents SDK의 최소 구성: Agent와 Runner를 실행한다."""

from pathlib import Path

from agents import Agent, Runner
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    agent = Agent(
        name="학습 도우미",
        instructions="AI 에이전트 개념을 한국어로 간결하게 설명하세요.",
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(agent, "에이전트와 일반 챗봇의 차이를 설명해줘.")
    print(result.final_output)


if __name__ == "__main__":
    main()
