import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage
import time


PROMPT = "What's trending news in Indonesia at the moment?. Share article link for each "

async def main():
    #agentic loop streams messages as claude works
    async for message in query(
        prompt = PROMPT,
        options = ClaudeAgentOptions(
            allowed_tools = ["WebSearch"],
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print("Claude Reasoning:", end =" ")
                    print(block.text)#actual LLM response
                elif hasattr(block, "name"):
                    print(f"Tool: {block.name}")#the repeated tool calls
        elif isinstance(message, ResultMessage):
            # print(f"Done: {message.subtype}")
            continue

asyncio.run(main())