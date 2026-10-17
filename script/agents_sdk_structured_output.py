"""Pydantic 모델을 이용해 에이전트 결과 형식을 지정한다."""

from pathlib import Path

from agents import Agent, Runner
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class LessonSummary(BaseModel):
    topic: str
    summary: str
    key_points: list[str]


def main() -> None:
    agent = Agent(
        name="학습 요약 에이전트",
        instructions="주어진 주제를 초보자에게 설명하고 핵심 포인트를 정리하세요.",
        output_type=LessonSummary,
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(agent, "함수 도구가 무엇인지 설명해줘.")
    summary = result.final_output
    print(f"주제: {summary.topic}")
    print(f"요약: {summary.summary}")
    print("핵심 포인트:")
    for point in summary.key_points:
        print(f"- {point}")


if __name__ == "__main__":
    main()
