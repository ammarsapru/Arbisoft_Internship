# Week 4 — Prompts

Prompts used across the week-4 agent experiments, with notes on what each
one exercises.

## Research agent (`research-agent/`)

### System prompt (`research_agent.py`)

```text
You are a research agent. You have these skills:
- web_search: search the web for current information (always cite links)
- read_file: read local .txt/.md/.pdf files
- remember_fact / recall_facts: session key-value memory
When you learn an important fact (from a file or a search) that later steps
might need, store it with remember_fact. When answering follow-up questions,
check recall_facts before searching again. Answer concisely and cite sources.
```

Design notes:
- Names each skill and says **when** to use it — tool *descriptions* say what
  a tool does, but the system prompt sets the workflow policy (store facts
  proactively, recall before re-searching, always cite).
- Keeps output policy ("concise, cite sources") in the system prompt rather
  than repeating it in every user prompt.

### Demo turn 1 — files → memory (`demo.py`)

```text
Read sample_notes.txt and sample_doc.pdf. Store the important facts
(client HQ city, offsite month, team size, budget cap, hotel budget)
in memory. Then briefly confirm what you stored.
```

Exercises: `read_file` on both .txt and .pdf, then `remember_fact` ×5.

### Demo turn 2 — multi-hop question (`demo.py`)

```text
Now the multi-hop question: based on what you remember (do not ask me
to repeat anything), find one recent news item about the client's HQ
city that could affect our offsite travel, and tell me whether the
per-night hotel budget from the brief looks realistic for that city.
Cite your sources.
```

Exercises the full multi-hop chain in one question:
1. `recall_facts` — which city? what budget? (memory, hop 1)
2. `web_search` — recent news about that city (hop 2)
3. `web_search` — hotel prices in that city (hop 3)
4. Synthesis — compare search results against the remembered budget.

"Do not ask me to repeat anything" forces the agent to rely on session
memory instead of asking the user.

## Earlier experiments (`first-agent/`)

| File | Prompt | What it demonstrated |
|---|---|---|
| `main.py` | `What is the Claude Agent SDK capablities` | Basic `query()` loop, message types |
| `webSearchTool.py` | `What's trending news in Indonesia at the moment?. Share article link for each` | Built-in WebSearch tool, repeated tool calls |
| `mcp_server_serp.py` | system: `Always use the SerpApi MCP server for web search`; user: `Find me a hotel under $100 in Bay Area next week` | Remote MCP server config + `allowed_tools` |

## Prompting lessons learned this week

- Asking for *N things with a link for each* makes the agent issue several
  search calls — one `ToolUseBlock` per search, which is why "Tool: WebSearch"
  prints repeatedly.
- Permission denials are silent killers: if `allowed_tools` doesn't cover a
  tool the prompt implies (e.g. pattern `mcp_serpapi__*` instead of
  `mcp__serpapi__*`), the agent burns turns getting denied and falls back to
  its training knowledge.
- Put stable policy in the system prompt, per-task detail in the user prompt —
  the system prompt is cached across turns.
