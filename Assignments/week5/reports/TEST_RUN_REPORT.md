# End-to-End Test Run Report

Date: 2026-07-09 (all runs against live SerpApi + Anthropic API, real cost incurred)

## What was tested

Five real pipeline runs through `uv run python -m fin_analyst.cli "<company>" --period "<period>"`,
chosen to exercise the main path plus every guardrail/edge case built into the design:

| # | Command | Purpose | Result |
|---|---|---|---|
| 1 | `"Apple" --period "5 years"` | Main path, exact-window request | Report generated |
| 2 | `"Tesla" --period "10 years"` | Period exceeding Google Finance's max window (5Y) → should fall back to MAX with a visible caveat | Report generated, caveat correctly surfaced in the exec summary |
| 3 | `"Zzqxplorion Nonexistent Ventures"` | Company that doesn't exist | Cleanly aborted at ticker resolution, **zero LLM cost** |
| 4 | `"SpaceX"` | Ticker resolution returns a *technically valid but wrong* ticker (see below) | Supervisor's semantic guardrail caught it and aborted before producing a misleading report |
| 5 | `"Apple"` (no `--period`) | Default period path | Report generated, defaulted to 1Y as designed |

All 5 raw console transcripts are saved alongside this file (`e2e_test_run_*_raw.txt`). All 5 trace files are in `traces/` and can be replayed with `uv run python -m fin_analyst.tracing.replay <run_id>`.

## Cost & token usage (real, not estimated)

| Run | LLM calls | Tokens in/out | Est. cost | Wall latency |
|---|---|---|---|---|
| 1. Apple 5Y | 4 | 4,282 / 1,467 | $0.0323 | 121.3s |
| 2. Tesla 10Y (MAX) | 4 | 4,463 / 1,665 | $0.0353 | 281.0s |
| 3. Fake company | 0 | 0 / 0 | $0.0000 | 28.7s |
| 4. SpaceX (aborted) | 1 | 910 / 128 | $0.0046 | 53.7s |
| 5. Apple default | 4 | 4,279 / 1,456 | $0.0319 | 123.7s |
| **Total (5 runs)** | **13** | **13,934 / 4,716** | **$0.1042** | - |

**Cost per successful report: ~$0.032.** The two aborted runs cost $0.0046 and $0.00 respectively — the guardrails that stop the pipeline early are also what keeps failed/invalid queries cheap, which is the point of putting them where they are in the graph (see docs/07-cost-latency-strategy.md and docs/08-structured-outputs-guardrails.md).

**Model tiering held up as designed**: Worker A (extraction) made 0 LLM calls (pure tool orchestration, as planned — see docs/07). Worker C's executive-summary generation used the fast tier (claude-haiku). The supervisor's validation gates and Worker B's news classification used the strong tier (claude-sonnet-5), which is where almost all of the token spend concentrated (news classification alone was ~2,200 input / ~1,000 output tokens per run — batching all 15 articles into one call, as designed, rather than 15 separate calls).

**Latency note**: run 2 (Tesla, MAX window) took much longer (281s vs. ~122s) than the 5Y runs — the MAX window returns a much larger price-history series, which increases MCP payload size and the news/supervisor LLM calls' context. This is a real, measured latency cost of requesting very long history, not a bug.

## Bugs found and fixed during this test pass

Real issues only found by running against live data, not visible from schema design alone:

1. **`engine=google_finance` rejects plain company names outright** (no fuzzy matching, no `suggestions` array as the docs implied) — `resolve_ticker` had to be redesigned so the web-search fallback is the *primary* path for a free-text name, not a secondary one.
2. **`engine=google_finance` returns different fields depending on whether `window` is passed** — fundamentals (`knowledge_graph`, `financials`) only appear on the window-less call. `get_stock_financials` now makes two internal calls to get both.
3. **`@computed_field` broke MCP structured-output validation.** FastMCP's output-schema validation uses pydantic's default (validation-mode) JSON Schema, which excludes computed fields from `properties` — combined with `extra="forbid"`, this made `net_margin_pct` and `outperformance_pct` fail with "Additional properties are not allowed" the moment they were nested inside an MCP tool's return type. Fixed by converting both to stored fields set via `@model_validator(mode="after")` instead of `@computed_field` — documented in `schemas/finance.py` so it isn't silently reintroduced.
4. **`langchain-mcp-adapters` serializes `list[T]`-returning tools as one content block *per list element*, not one block containing a JSON array** (confirmed by direct inspection — `get_company_news` returning 15 articles came back as 15 separate content blocks). The single-object unwrap helper silently mis-parsed this (iterating a dict's keys as if they were list items) until a dedicated `_unwrap_list` was added.
5. **A structured-output field's `max_length` constraint was violated by the model** (the supervisor's `reason` field exceeded 280 chars), which crashes `.with_structured_output()` with a raw pydantic `ValidationError` and no built-in retry. Added `agents/structured_call.py`: one retry with a "keep it brief" nudge, then a safe fallback default rather than crashing the whole pipeline.
6. **Rich console markup collision**: `console.print(f" - [{stage}] ...")` silently ate the `[stage]` text because Rich interprets square brackets as style tags. Fixed by switching to `f"{stage}: ..."`.

None of these were guessable from documentation alone — this is exactly why the plan called for testing against the live API before building the full stack, and why the docs' "Our Implementation" sections cite this test pass as the source of truth.

## A genuinely interesting result: the SpaceX run

`resolve_ticker("SpaceX")` found a knowledge-panel match for ticker `SPCX:NASDAQ`, and that ticker **is** live and tradeable on Google Finance as of the current date in this environment — so the deterministic verification step (which just checks "does this ticker exist") passed. But the supervisor's semantic validation gate (a separate LLM call reasoning about whether the result actually makes sense) correctly flagged that this didn't plausibly match "SpaceX" given its own knowledge, and aborted the pipeline rather than generating a report against what could easily be an unrelated or mismatched entity. This is the guardrail architecture working exactly as designed: a deterministic check and a semantic check catching different classes of error, neither able to catch what the other catches. See `docs/08-structured-outputs-guardrails.md`.

## How to run this yourself

```
uv run python -m fin_analyst.cli "<company name>" --period "<e.g. '5 years', 'YTD', '1 month'>"
```

- Output Excel report lands in `reports/<TICKER>_<timestamp>.xlsx`.
- Every run prints a `run_id` and its live cost/token summary at the end.
- Replay any run's full trace (every MCP tool call and every LLM call, in order, with latency and tokens): `uv run python -m fin_analyst.tracing.replay <run_id>`.
- To manually poke at the MCP server's tools/resource/prompt directly (independent of the agent pipeline), it's registered with Claude Code as `financial-analyst` — open a new Claude Code session in this project and its tools will be available.
