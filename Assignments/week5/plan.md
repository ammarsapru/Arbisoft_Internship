# Financial Analyst MCP + Multi-Agent System — Design & Validation Plan

Status: **core pipeline built, tested end-to-end against live APIs, working.** See
`reports/TEST_RUN_REPORT.md` for real test results and `docs/*.md` for the underlying MCP/agent
concepts this project is built to demonstrate.

## Context

This project has two deliverables: (1) eight topic explainer docs covering MCP fundamentals
through multi-agent guardrails (`docs/`), each with an "Our Implementation" section tying the
concept to real code in this repo, and (2) a working system — a custom MCP server wrapping three
SerpApi endpoints (Google Finance Markets, Google Finance, Google News, plus Google web search as
a ticker-resolution fallback) driven by a LangGraph supervisor + 3-worker pipeline that turns a
company name into a multi-sheet Excel financial report.

The four graded requirements this satisfies: an MCP server with ≥1 resource + ≥1 tool (it has 2
resources, 6 tools, 1 prompt), a client connection (both Claude Code and a custom
`MultiServerMCPClient`-based agent client), a supervisor routing to ≥2 sub-agents (3: Financial
Data Extraction, News Impact Analyst, Report Formatting), and a tracing layer over every tool call
(a unified JSONL trace spanning both the MCP server process and the LangGraph agent process).

The fifth tool, `generate_financial_report`, was added after the initial build: the first four
tools only expose raw data-fetching, so a client with no direct code/filesystem access to this
project (a fresh Claude Code session, or a remotely-connected Claude.ai) had no way to trigger the
actual supervisor+worker pipeline or get an Excel file out — only the CLI could. It wraps
`agents.pipeline.run_pipeline()` as a single tool call; internally this means the MCP server
launches a second copy of itself as a subprocess to call its own other four tools, which is
unusual but correct and confirmed working live (`reports/test_generate_report_tool_raw.txt`). It
also takes an `output_directory` parameter, added after discovering (live) that a `--scope
user`-registered server always wrote reports to its own directory regardless of the calling
session's location — MCP tool calls carry no ambient "caller's cwd," so callers now pass it
explicitly as an absolute path.

Two more additions came from directly probing what the server actually exposes to an agent client:
a sixth tool, `get_analyst_prompt`, duplicating the `financial_analyst_briefing` **prompt**'s
content — discovered live that the MCP prompt primitive is host-UI-only (surfaced for a human to
pick, e.g. a slash command) and has no mechanism for the calling model to fetch it itself, so an
agent had no way to reach that text at all without this tool. And a second resource,
`top-companies://top20`, a static hand-curated reference list (no data source exists in this
project for ranking companies against each other, so it's explicitly disclosed as curated, not
live-ranked) — added specifically because it needs no prior tool call, unlike `finance-report://`,
whose cache-population gap (populated in a spawned child process's memory when called via
`generate_financial_report`, not the outer process's) was found and documented but left unfixed.

## Data reality, validated live (not just from docs)

The original design was based on SerpApi's published documentation, which turned out to be
incomplete on two important points — discovered by hitting the live API before building the rest
of the stack:

- **`engine=google_finance` rejects plain company names outright** — no fuzzy matching, no
  `suggestions` fallback. It only works with an exact `TICKER:EXCHANGE` string. This means ticker
  resolution for a free-text company name has to go through SerpApi's `google` web-search engine
  (parsing the knowledge panel's `"EXCHANGE: TICKER"` field) as the *primary* path, not a
  secondary fallback as originally assumed — and every web-search candidate is then verified
  against a real `google_finance` call before being trusted (see the SpaceX case study in
  `reports/TEST_RUN_REPORT.md` for why this verification step matters).
- **`engine=google_finance` returns a different subset of fields depending on whether `window` is
  passed.** Window-less calls return `knowledge_graph` (valuation stats, company profile) +
  `financials` (full income statement/balance sheet/cash flow — confirmed live to go back to
  2000 for a mature ticker, quarterly + annual) + embedded `news_results`. Windowed calls return
  only `graph` (price series) + `summary`. `get_stock_financials` therefore makes two SerpApi
  calls internally to assemble one complete `FinancialBundle`.
- **Embedded `news_results` (on the finance response) lack `iso_date`**, only a relative string
  ("19 minutes ago") — unusable for recency-decay weighting. `get_company_news` uses the
  dedicated `google_news` engine instead, which does return `iso_date`.
- Google Finance's financial statements turned out to be **much deeper than the original "curated
  subset, not full 10-K depth" caveat implied** — live testing on AAPL returned 34 income
  statement periods (8 quarters + 26 years back to 2000), 18 balance sheet and cash flow periods
  each. Still not equivalent to a full SEC filing, but a genuinely substantial fundamentals
  history, not a thin summary.

## Financial analysis scope

| Source | Analysis performed |
|---|---|
| Finance API `summary` | Current price, today's movement, after-hours |
| Finance API `graph` (window 1D→MAX) | Technicals computed client-side: period return, volatility (stdev of daily returns), max drawdown, SMA/EMA — Google Finance has no technicals endpoint of its own |
| Finance API `knowledge_graph` | Valuation snapshot (market cap, P/E, 52-wk range, etc.) + company profile |
| Finance API `financials` | Fundamental trends: net margin (computed), full statement history exposed in the Fundamentals sheet |
| Finance Markets (`trend=indexes`) | Relative performance: stock's period return vs. its home index (NASDAQ→Nasdaq, NYSE→S&P 500) |
| News API | Per-article LLM sentiment + magnitude classification, recency-decay weighted vs. last close, aggregated into a News Impact Score |

**Explicitly out of scope**: analyst price targets/estimates, institutional ownership, insider
trading, options data, real-time streaming quotes. Google Finance's financials are a curated
summary of what its own UI shows, not a full filing.

**Current snapshot vs. user-defined period**: both are mandatory on every run. `--period` accepts
free text and is mapped to the nearest supported window (`1D/5D/1M/6M/YTD/1Y/5Y/MAX`) by
`agents/period.py`'s `parse_period()`; any request exceeding what Google Finance supports (e.g.
"10 years") falls back to `MAX` with an explicit caveat that is carried through
`FinancialBundle.period` and surfaced in both the Excel Overview sheet and the LLM-generated
executive summary — confirmed working in test run 2 (Tesla, 10 years).

## Architecture

```
Company name + period
   │
   ▼
[extraction worker] -- resolve_ticker -> get_stock_financials (2 internal SerpApi calls) --> FinancialBundle
   │   (pure tool orchestration, NO LLM call - see docs/07-cost-latency-strategy.md)
   ▼
[supervisor: validate_after_extraction] -- strong-tier LLM semantic check --> proceed / abort
   │
   ▼
[news impact worker] -- get_company_news --> batched LLM sentiment/magnitude classification --> NewsImpactBundle
   ▼
[supervisor: validate_after_news] -- strong-tier LLM semantic check --> proceed / abort
   ▼
[formatting worker] -- fast-tier LLM executive summary + XlsxWriter workbook --> ReportOutput
   ▼
[supervisor: validate_after_formatting] -- deterministic file-exists check --> done
```

Every MCP tool call (server-side, via `tracing/mcp_middleware.py`) and every LangGraph node / tool
/ LLM call (agent-side, via `tracing/callbacks.py`'s `BaseCallbackHandler`) writes a `TraceEvent`
to the same `traces/<run_id>.jsonl` file — unified across the process boundary by injecting
`TRACE_RUN_ID` into the MCP server subprocess's environment when the agent launches it
(`agents/mcp_client.py`).

## Pydantic & LangChain usage

- **Two-layer raw→domain schemas** at every SerpApi boundary (`mcp_server/schemas/raw/` are
  loose/`extra=ignore`; `mcp_server/schemas/finance.py` etc. are strict/`extra=forbid`), so
  upstream API drift can't silently corrupt downstream logic.
- **Discriminated union for ticker resolution outcomes** (`Resolved | Ambiguous |
  NotPubliclyListed | LookupFailed` in `schemas/report.py`) — the supervisor and CLI branch on
  `.outcome`, never on `None`-checking.
- **`.with_structured_output()`** for every LLM call producing data: news impact judgments
  (batched, one call for all articles) and the supervisor's proceed/abort decision.
- **One real lesson learned and documented**: `@computed_field` looked like the natural pydantic
  pattern for derived values (`net_margin_pct`, `outperformance_pct`), but broke FastMCP's
  output-schema validation the moment those fields were nested inside an MCP tool's return type —
  see the "Bugs found" section of `reports/TEST_RUN_REPORT.md`. Fixed by computing them via
  `@model_validator(mode="after")` into stored fields instead. `NewsImpactScore.composite_score`
  and `NewsImpactBundle.aggregate_impact_score` still use `@computed_field` safely, because those
  types never cross an MCP tool boundary (constructed entirely in the agent layer).
- **LangGraph `StateGraph` typed on a Pydantic `PipelineState`**, with `validation_failures` using
  an `Annotated[list, operator.add]` reducer so failures accumulate across stages rather than
  overwrite.
- **Structured-output resilience**: a live validation failure (the supervisor's `reason` field
  exceeding its `max_length`) proved that `.with_structured_output()` can still raise even with a
  schema constraining generation. `agents/structured_call.py` wraps every such call with one retry
  and a safe fallback rather than letting a formatting slip crash the whole pipeline.

## Cost & latency (real numbers, not estimates)

See `reports/TEST_RUN_REPORT.md` for the full breakdown. Headline: **~$0.032 per successful
report**, **$0.00–0.005 for a query that gets caught by a guardrail early** (not-listed company:
$0; bad-resolution catch: $0.0046) — the guardrails that stop the pipeline early are also what
keeps invalid queries cheap. Model tiering held: extraction made zero LLM calls (pure tool
orchestration), formatting's exec summary used the fast tier, and the strong tier was reserved for
the two things that need judgment — supervisor validation and news sentiment classification.

## What's built vs. remaining

Built and tested end-to-end against live SerpApi + Anthropic APIs: MCP server (all 4 tools, the
resource, the prompt), the Claude Code registration, the custom `MultiServerMCPClient` agent
connection, the full LangGraph supervisor+3-worker graph with validation gates, the Excel builder
(5 sheets + price chart), the unified tracing layer + replay CLI, the cost/token accounting, and
the CLI entrypoint.

Remaining / possible follow-ups (not required by the graded scope, noted for completeness):
OpenTelemetry-standard span export (currently a custom lightweight tracer, per the confirmed
design decision), a persistent MCP client session (currently each tool call's subprocess lifecycle
is managed by `langchain-mcp-adapters` per-call, which is simple but adds process-launch latency —
acceptable at this project's scale), and finer-grained LangGraph node names in the `agent_node`
trace layer (currently shows as generic "chain" spans; tool-level and LLM-level trace events have
clean, specific names and carry the real debugging value).

### Bug fixes (post-initial-build), all confirmed live

1. **Relative Performance period mismatch**: `benchmark_period_return_pct` used to come from
   `get_market_snapshot()`'s always-current-day index movement, silently compared against the
   stock's actual multi-period return whenever the window wasn't `1D`. Fixed by fetching the
   benchmark index's own windowed price history (same `google_finance` engine, same `window`) and
   computing its period return the same way the stock's is computed, using hardcoded stable index
   codes (`.IXIC:INDEXNASDAQ`, `.INX:INDEXSP`) rather than discovering them via
   `get_market_snapshot()`.
2. **That hardcoding turned out to be necessary, not just cleaner**: mid-session, live testing
   found `engine=google_finance_markets` had stopped returning its `markets` object entirely
   (reproduced 3x, a real third-party behavior change, not a caching artifact) — a live example of
   why this project's tools are designed to degrade to `None`/typed-failure rather than crash or
   fabricate a number when an upstream source misbehaves (see `docs/08`).
3. **`finance-report://{ticker}` cache not populated via `generate_financial_report`**: its
   internal pipeline called `get_stock_financials` through a separately-spawned child server
   subprocess, populating that child's own in-memory cache, not the outer process's. Fixed by
   having `generate_financial_report` cache `state.financial_bundle` directly once `run_pipeline()`
   returns, in the process that actually serves the resource.
4. Verifying fix #3 required noticing that `MultiServerMCPClient`'s `get_tools()`/`.ainvoke()`
   convenience API opens a fresh subprocess per call — unlike a real host (Claude Code), which
   holds one persistent connection for a session's lifetime. Testing the tool call and the
   resource read as two separate throwaway sessions masked the fix; testing them within one
   persistent session (matching real usage) confirmed it.
