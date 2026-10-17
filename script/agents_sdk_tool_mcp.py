"""로컬 stdio MCP 파일 서버에서 카페 메뉴를 읽는 예제.

필요 조건: Node.js와 npx. npx가 공식 filesystem MCP 서버를 실행한다.
"""

import asyncio
from pathlib import Path

from agents import Agent, ModelSettings, Runner
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    # MCP 서버와 stdio(표준 입력·출력)로 통신하는 Agents SDK 클라이언트입니다.
    from agents.mcp import MCPServerStdio

    menu_dir = Path(__file__).resolve().parent / "samples"
    menu_file = (menu_dir / "cafe_menu.md").resolve()
    # MCPServerStdio: MCP 서버 프로세스를 실행하고, 표준 입력·출력으로 연결을 유지
    async with MCPServerStdio(
        name="카페 메뉴 MCP 서버",
        params={
            "command": "npx",
            # @modelcontextprotocol/server-filesystem: 지정한 폴더의 파일과 폴더를 다루는 MCP 서버
            # (읽기, 목록 확인, 파일 쓰기, 생성, 이동 같은 기능을 제공)
            "args": ["-y", "@modelcontextprotocol/server-filesystem", str(menu_dir)],
        },
    ) as server:
        agent = Agent(
            name="카페 메뉴 안내 에이전트",
            instructions=(
                f"답변 전에 반드시 filesystem MCP의 read_file 도구로 {menu_file} 파일을 읽으세요. "
                "파일을 읽지 못했다면 메뉴가 없다고 추측하지 말고 도구 오류를 설명하세요. "
                "읽은 메뉴에 적힌 정보만으로 추천하고, "
                "가격이나 재료를 지어내지 말고 추천 이유도 짧게 설명하세요."
            ),
            mcp_servers=[server],
            model="gpt-4.1-mini",
            # MCP 도구를 실제로 호출하도록 강제
            model_settings=ModelSettings(tool_choice="required"),
        )
        result = await Runner.run(agent, f"{menu_file}을 읽고 따뜻하고 달지 않은 음료 하나를 추천해줘.",)
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
