import os
from dotenv import load_dotenv
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage


load_dotenv()

SERP_API_KEY = os.environ.get("SERP_API_KEY")

async def main():
    SYSTEM_PROMPT = "Always use the SerpApi MCP server for web search"
    USER_PROMPT = "Find me a hotel under $100 in Bay Area next week"

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers= {
            "serpapi": {
                "type": "http",
                "url": "https://mcp.serpapi.com/"+ SERP_API_KEY +"/mcp"
            }
        },
        allowed_tools= ["mcp__serpapi__search"],
    )

    async for message in query(
        prompt = USER_PROMPT,
        options = options,
    ):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            print(message.result)

asyncio.run(main())
