"""함수 도구와 실행 context를 에이전트에 전달하는 예제."""

from dataclasses import dataclass
from pathlib import Path

from agents import Agent, RunContextWrapper, Runner, function_tool
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass
class AppContext:
    """도구가 사용할 애플리케이션 상태 예시."""

    course_catalog: dict[str, str]


@function_tool
def find_lesson(ctx: RunContextWrapper[AppContext], topic: str) -> str:
    """강의 주제에 해당하는 로컬 실습 파일을 찾는다."""
    return ctx.context.course_catalog.get(topic.lower(), "해당 주제의 실습을 찾지 못했습니다.")


def main() -> None:
    context = AppContext(
        course_catalog={
            "agent": "script/agents_sdk.py",
            "tool": "script/agents_sdk_tools.py",
            "handoff": "script/agents_sdk_handoff.py",
            "guardrail": "script/agents_sdk_guardrails.py",
            "structured output": "script/agents_sdk_structured_output.py",
        }
    )
    agent = Agent[AppContext](
        name="실습 안내 에이전트",
        instructions=(
            "이 프로젝트의 실습 파일 위치를 안내합니다. "
            "경로를 물으면 find_lesson 도구를 사용하고 결과에 없는 경로는 만들지 마세요."
        ),
        tools=[find_lesson],
        model="gpt-4.1-mini",
    )

    result = Runner.run_sync(agent, "tool 실습 파일은 어디 있어?", context=context)
    print(result.final_output)


if __name__ == "__main__":
    main()
