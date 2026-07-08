"""
Demo: a single research agent answers a multi-hop question using
file reading (.txt + .pdf), session memory, web search, and hook logging.

Turn 1 -> read both local files, store the key facts in memory.
Turn 2 -> (multi-hop) recall the client's HQ city from memory, web-search
          recent news about it, and combine that with the budget from the
          PDF to give a recommendation. The agent is NOT re-told the city
          or budget in turn 2 — it must recall them from the session.

Every tool call is logged with a timestamp to tool_calls.log by the hooks.
"""

import asyncio
import sys

# Windows consoles default to cp1252, which crashes on Unicode in agent output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from research_agent import LOG_FILE, MEMORY, build_options

TURN_1 = (
    "Read sample_notes.txt and sample_doc.pdf. Store the important facts "
    "(client HQ city, offsite month, team size, budget cap, hotel budget) "
    "in memory. Then briefly confirm what you stored."
)

TURN_2 = (
    "Now the multi-hop question: based on what you remember (do not ask me "
    "to repeat anything), find one recent news item about the client's HQ "
    "city that could affect our offsite travel, and tell me whether the "
    "per-night hotel budget from the brief looks realistic for that city. "
    "Cite your sources."
)


async def run_turn(client: ClaudeSDKClient, prompt: str, label: str) -> None:
    print(f"\n{'=' * 70}\n{label}: {prompt[:80]}...\n{'=' * 70}")
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"\n[agent] {block.text}")
                elif isinstance(block, ToolUseBlock):
                    print(f"[tool call] {block.name} -> {str(block.input)[:120]}")
        elif isinstance(message, ResultMessage):
            print(f"\n[done] status={message.subtype} turns={message.num_turns} "
                  f"cost=${message.total_cost_usd:.4f}")


async def main() -> None:
    async with ClaudeSDKClient(options=build_options()) as client:
        await run_turn(client, TURN_1, "TURN 1 (files -> memory)")
        print(f"\n[memory store now contains] {MEMORY}")
        await run_turn(client, TURN_2, "TURN 2 (recall -> search -> synthesize)")

    print(f"\n[hook log] tool calls were logged to: {LOG_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
