import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions,AssistantMessage, ResultMessage

async def main():
    async for messages in query(
        prompt = "What is the Claude Agent SDK capablities",
        options = ClaudeAgentOptions(#can choose a specific tool by adding allowed_tools option.
            #there is also disallowed_tools to prevent the agent from using a specific tool.
            allowed_tools = ["Read", "Edit", "Glob"],
            permission_mode = "acceptEdits"
        ),
    ):
        if isinstance(messages, AssistantMessage):
            for block in messages.content:
                if hasattr(block, "text"):
                    print("Claude Reasoning:", end ="")
                    print(block.text)
                elif hasattr(block, "name"):
                    print(f"Tool: {block.name}")
        elif isinstance(messages, ResultMessage):
            print(f"Done: {messages.subtype}")

        # print(messages)
        # print(messages.AssistantMessage)

asyncio.run(main())