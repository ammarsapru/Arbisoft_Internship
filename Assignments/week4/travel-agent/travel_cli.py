"""
Flight Research Agent - interactive CLI.

Mode 1: research from a travel-plan file (.pdf / .txt / .md, default trip_plan.pdf)
Mode 2: enter the trip details manually (budget, start/end + dates, trip type)

Either way the constraints are handed to the agent, which applies them as
search-tool parameters and asks clarifying questions when something is
ambiguous. The session persists, so you can keep asking follow-up questions
(see questions.md for a demo script). Commands: /memory /log /quit
"""

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from travel_agent import LOG_FILE, MEMORY, build_options


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val or default


def kickoff_from_file() -> str:
    path = ask("Travel plan file (.pdf/.txt/.md)", "trip_plan.pdf")
    return (
        f"Read the travel plan file '{path}'. Extract ALL constraints "
        "(budget, start location, trip type, every leg's destination, dates and "
        "desired arrival times, hotel budgets) and store them in memory. "
        "If anything required is missing or ambiguous, ask me first. Then "
        "research flights and hotels for every leg, applying the constraints "
        "as tool parameters, and give me a per-leg proposal plus a total-vs-"
        "budget verdict."
    )


def kickoff_from_manual() -> str:
    print("\nEnter your trip details (leave blank if unknown - the agent will ask):")
    budget = ask("Total budget in USD")
    start_loc = ask("Start city, country")
    start_date = ask("Departure date (YYYY-MM-DD)")
    end_loc = ask("Destination city, country")
    end_date = ask("Date at destination / return date (YYYY-MM-DD)")
    trip_type = ask("Trip type (round_trip / one_way)", "round_trip")
    parts = [
        "Research a trip with these constraints:",
        f"- total budget USD: {budget or 'NOT PROVIDED'}",
        f"- start location: {start_loc or 'NOT PROVIDED'}",
        f"- departure date: {start_date or 'NOT PROVIDED'}",
        f"- destination: {end_loc or 'NOT PROVIDED'}",
        f"- end/return date: {end_date or 'NOT PROVIDED'}",
        f"- trip type: {trip_type}",
        "Store the constraints in memory. Ask me about anything missing or "
        "ambiguous before searching. Then search flights and hotels in "
        "parallel, applying the constraints as tool parameters, and report "
        "options plus a total-vs-budget verdict.",
    ]
    return "\n".join(parts)


async def stream_response(client: ClaudeSDKClient) -> None:
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"\nagent> {block.text}")
                elif isinstance(block, ToolUseBlock):
                    print(f"  [tool] {block.name} {str(block.input)[:110]}")
        elif isinstance(message, ResultMessage):
            print(f"  [turn done: {message.subtype}, cost ${message.total_cost_usd:.4f}]")


async def main() -> None:
    print("=" * 60)
    print(" Flight Research Agent")
    print("=" * 60)
    print(" 1) Research from a travel-plan file (PDF/TXT)")
    print(" 2) Enter trip details manually")
    mode = ask("Choose mode", "1")
    kickoff = kickoff_from_file() if mode == "1" else kickoff_from_manual()

    async with ClaudeSDKClient(options=build_options()) as client:
        await client.query(kickoff)
        await stream_response(client)

        # follow-up loop: multi-hop questions, clarification answers, etc.
        print("\nAsk follow-up questions (/memory /log /quit):")
        while True:
            try:
                user = input("\nyou> ").strip()
            except EOFError:
                break
            if not user:
                continue
            if user == "/quit":
                break
            if user == "/memory":
                print(f"  MEMORY = {MEMORY}")
                continue
            if user == "/log":
                lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
                print(f"  {len(lines)} log lines, last 5:")
                for line in lines[-5:]:
                    print(f"    {line}")
                continue
            await client.query(user)
            await stream_response(client)

    print(f"\nBye. Full tool-call audit log: {LOG_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
