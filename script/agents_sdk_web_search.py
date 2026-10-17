"""OpenAI 호스팅 Web Search tool을 Agents SDK에서 사용하는 예제."""

from pathlib import Path

from agents import Agent, Runner, WebSearchTool
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    agent = Agent(
        name="웹 조사 에이전트",
        instructions="웹을 검색해 질문에 답하고, 확인한 출처를 함께 설명하세요.",
        tools=[WebSearchTool()],
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(agent, "OpenAI Agents SDK 공식 Quickstart의 핵심 내용을 요약해줘.")
    print(result.final_output)


if __name__ == "__main__":
    main()
