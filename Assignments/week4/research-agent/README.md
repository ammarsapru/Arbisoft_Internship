# Research Agent — Week 4 Assignment

A single research agent (built on the Claude Agent SDK) that covers every
assignment item:

| Assignment item | Where |
|---|---|
| Web-search skill (SerpApi) | `web_search` tool in `research_agent.py` |
| Memory: recalls facts from earlier in the session | `remember_fact` / `recall_facts` tools + multi-turn `ClaudeSDKClient` in `demo.py` |
| Hook logging every tool call with timestamps | `log_tool_call` (PreToolUse + PostToolUse) → `tool_calls.log` |
| File-read plugin (.txt / .pdf) | `read_file` tool (pypdf for PDFs) |
| Demo: multi-hop question using all of the above | `demo.py` (2 turns: files→memory, then recall→search→synthesize) |
| Topics notes | `../topics.txt` |
| prompts.md | `../prompts.md` |

## Files

- `research_agent.py` — tools, hooks, and agent configuration (in-process MCP server)
- `demo.py` — end-to-end multi-hop demo (run this)
- `test_tools.py` — direct unit tests for every tool + the hook (no agent, fast)
- `sample_notes.txt` / `sample_doc.pdf` — data the agent reads in the demo
- `make_sample_pdf.py` — regenerates `sample_doc.pdf`
- `tool_calls.log` — timestamped log written by the hooks (generated at runtime)

## Setup & run

Requires: `claude-agent-sdk`, `requests`, `python-dotenv`, `pypdf` (all installed),
and `SERP_API_KEY` in `../first-agent/.env` (already present).

```powershell
python test_tools.py   # unit-level: 6 checks, includes a live SerpApi call
python demo.py         # full agent demo (~$0.15 in API usage)
```

## Verified results (2026-07-06)

- `test_tools.py`: **6/6 checks passed** (txt read, pdf read, error paths,
  memory round-trip, live SerpApi search, hook log line format)
- `demo.py`: turn 1 read both files and stored 5 facts; turn 2 recalled the
  city + budget from memory without being re-told, ran 2 web searches
  (Jakarta travel news + hotel prices), and synthesized a cited answer.
  Total cost ≈ $0.14. `tool_calls.log` captured every call with timestamps.
