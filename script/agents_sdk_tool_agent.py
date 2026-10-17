"""직접 정의한 specialist Agent를 manager Agent의 tool로 활용한다."""

from pathlib import Path

from agents import Agent, Runner
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    research_agent = Agent(
        name="역사 조사 에이전트",
        instructions="요청받은 역사 주제의 핵심 사실을 간결하게 정리하세요.",
        model="gpt-4.1-mini",
    )

    tutor_agent = Agent(
        name="역사 튜터",
        instructions=(
            "학습자에게 역사 질문을 설명하세요. "
            "필요한 경우 research_history tool로 조사한 뒤, 결과를 한국어로 풀어 설명하세요."
        ),
        tools=[
            research_agent.as_tool(
                tool_name="research_history",
                tool_description="역사 주제의 핵심 사실을 조사한다.",
            )
        ],
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(tutor_agent, "훈민정음 창제의 의미를 알려줘.")
    print(result.final_output)


if __name__ == "__main__":
    main()
