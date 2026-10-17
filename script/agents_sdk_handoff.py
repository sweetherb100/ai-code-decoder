"""Handoff와 agent-as-tool 두 가지 에이전트 협업 패턴을 보여준다."""

from pathlib import Path

from agents import Agent, Runner
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def run_handoff_example() -> None:
    history_agent = Agent(
        name="역사 전문가",
        handoff_description="역사 질문에 답하는 전문 에이전트",
        instructions="역사 질문에 한국어로 간결하고 정확하게 답하세요.",
        model="gpt-4.1-mini",
    )
    triage_agent = Agent(
        name="질문 분류 에이전트",
        instructions="역사 질문은 역사 전문가에게 전달하고, 다른 질문은 직접 답하세요.",
        handoffs=[history_agent],
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(triage_agent, "세종대왕의 대표적인 업적을 알려줘.")
    print("[handoff]")
    print(result.final_output)
    print(f"응답한 에이전트: {result.last_agent.name}")


def run_agent_as_tool_example() -> None:
    history_agent = Agent(
        name="역사 조사 에이전트",
        instructions="요청된 역사 주제를 세 가지 핵심 사실로 정리하세요.",
        model="gpt-4.1-mini",
    )
    writing_agent = Agent(
        name="학습 답변 에이전트",
        instructions="역사 조사 에이전트의 결과를 바탕으로 학습자에게 설명하세요.",
        tools=[
            history_agent.as_tool(
                tool_name="research_history",
                tool_description="역사 주제의 핵심 사실을 조사한다.",
            )
        ],
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(writing_agent, "훈민정음 창제의 의미를 설명해줘.")
    print("\n[agent as a tool]")
    print(result.final_output)


def main() -> None:
    run_handoff_example()
    run_agent_as_tool_example()


if __name__ == "__main__":
    main()
