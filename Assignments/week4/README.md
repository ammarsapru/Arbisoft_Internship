# Week 4 — Agentic AI (Claude Agent SDK)

| Folder / file | What it is |
|---|---|
| `first-agent/` | First experiments with the Claude Agent SDK: `query()` basics, message types, built-in WebSearch, remote MCP server (SerpApi). Copy `.env.example` to `.env` and add your keys. |
| `research-agent/` | Assignment: research agent with a SerpApi web-search skill, session memory, timestamped tool-call logging hook, .txt/.pdf file-read plugin, and a multi-hop demo (`demo.py`). Unit tests in `test_tools.py`. |
| `travel-agent/` | Flight research agent + interactive CLI: Google Flights / Google Hotels tools with constraint parameters (budget, dates, trip type), PDF/manual trip intake, clarifying questions, memory, hook logging. Demo question script in `questions.md`. |
| `custom_api.py` | Original (buggy) flight-search tool attempt — kept for reference; rewritten properly in `travel-agent/travel_agent.py`. |
| `topics.txt` | Study notes covering all week-4 lecture topics, mapped to where each concept is implemented in this repo. |
| `prompts.md` | The prompts used across the week, with design notes and lessons learned. |

Requirements: Python 3.12, `claude-agent-sdk`, `requests`, `python-dotenv`, `pypdf`,
a Claude Code login (or `ANTHROPIC_API_KEY`), and a SerpApi key in `first-agent/.env`.
