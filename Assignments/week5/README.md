# Financial Analyst MCP + Multi-Agent System

A custom MCP server wrapping SerpApi's Google Finance Markets, Google Finance, and Google News
APIs (plus Google web search as a ticker-resolution fallback), driven by a LangGraph
supervisor + 3-worker agent pipeline that turns a company name into a multi-sheet Excel
financial report.

See `plan.md` for the full design/validation writeup and `docs/` for the underlying MCP/agent
concepts this project demonstrates.

## Setup

```
uv sync
```

Copy `.env.example` to `.env` and fill in `SERPAPI_KEY` / `SERP_API_KEY` and `ANTHROPIC_API_KEY`
(get a SerpApi key at serpapi.com, an Anthropic API key at console.anthropic.com — this is a
separate, metered key, not your Claude Code/claude.ai login).

## Run the full pipeline

```
uv run python -m fin_analyst.cli "Apple" --period "5 years"
```

- `--period` accepts free text ("YTD", "1 month", "10 years", ...) and is mapped to the nearest
  Google Finance window (1D/5D/1M/6M/YTD/1Y/5Y/MAX); if your request exceeds what's available,
  the report says so explicitly rather than silently substituting a different range.
- Output lands in `reports/<TICKER>_<timestamp>.xlsx` (5 sheets: Overview, Price & Technicals,
  Fundamentals, Relative Performance, News & Impact).
- Every run prints a `run_id` plus live token/cost accounting.
- See `reports/TEST_RUN_REPORT.md` for real cost figures and edge-case results from testing this
  against live data.

## Inspect a run's trace

```
uv run python -m fin_analyst.tracing.replay <run_id>
```

Prints every MCP tool call and every LLM call for that run, in order, with latency, status, and
token counts.

## Use the MCP server directly (independent of the agent pipeline)

The server is registered with Claude Code as `financial-analyst` (`claude mcp add ...` was
already run in this project). Open a new Claude Code session here and its tools
(`resolve_ticker`, `get_market_snapshot`, `get_stock_financials`, `get_company_news`), resource
(`finance-report://{ticker}`), and prompt (`financial_analyst_briefing`) are available directly,
independent of the LangGraph pipeline — useful for testing the server in isolation or for ad-hoc
lookups without generating a full report.

There's also a fifth tool, **`generate_financial_report(company_name, period)`**, which runs the
*entire* supervisor + 3-worker pipeline (including Excel generation) as a single tool call — ask a
fresh Claude Code session to "generate a financial report for Apple" and it can trigger the real
pipeline and hand back the report path + executive summary, without you having to run the CLI
yourself. It's slower (1-5 minutes) and costs real API money per call, same as the CLI.

To run it manually outside Claude Code: `uv run python -m fin_analyst.mcp_server.server`
(stdio transport; talks JSON-RPC over stdin/stdout).

## Run tests

```
uv sync --extra dev
uv run pytest
```

## Project layout

```
docs/            8 topic explainer docs (MCP fundamentals -> structured-output guardrails)
plan.md          Full design/validation writeup
reports/         Generated Excel reports + the test-run report + dev smoke-test logs
traces/          JSONL trace files per pipeline run (one file per run_id)
src/fin_analyst/
  mcp_server/    The MCP server: SerpApi client, schemas, tools, resource, prompt
  agents/        LangGraph supervisor + 3 workers, MCP client wiring, period parsing
  tracing/       TraceEvent model, JSONL tracer, MCP + LangChain callback hooks, replay CLI
  output/        XlsxWriter-based Excel report builder
  cli.py         Entrypoint
tests/           pytest suite (fixture-based, no live API calls)
```
