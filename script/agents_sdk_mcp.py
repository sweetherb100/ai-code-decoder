"""로컬 stdio MCP 파일 서버를 Agents SDK에 연결하는 예제.

필요 조건: Node.js와 npx. npx가 공식 filesystem MCP 서버를 실행한다.
"""

import asyncio
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    sample_dir = Path(__file__).resolve().parent / "samples"
    async with MCPServerStdio(
        name="강의 자료 파일 서버",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", str(sample_dir)],
        },
    ) as server:
        agent = Agent(
            name="파일 조사 에이전트",
            instructions=(
                "제공된 파일에서 정보를 찾아 답하세요. "
                "질문에 답할 때는 파일 내용을 읽고 근거를 간단히 덧붙이세요."
            ),
            mcp_servers=[server],
            model="gpt-4.1-mini",
        )
        result = await Runner.run(
            agent,
            "release_notes.md를 읽고 이번 버전의 주요 변경 사항을 요약해줘.",
        )
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
