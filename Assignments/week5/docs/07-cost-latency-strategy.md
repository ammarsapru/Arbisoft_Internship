# Cost & Latency Strategy Specific to Multi-Agent Systems

## Why multi-agent systems are expensive by default

Every hand-off is a new LLM call, and every LLM call in a pipeline that passes forward "everything so far" grows the input token count linearly with pipeline depth — a 3-worker pipeline naively re-sending the full running transcript to each subsequent call pays for the same tokens repeatedly. Multi-agent systems multiply this: the supervisor call itself costs tokens on *every* hand-off, on top of each worker's own work.

## Where to spend tokens (the actual strategy)

The lever that matters most isn't "use a cheaper model everywhere" (that trades cost for quality where quality matters) — it's **matching model strength to the actual difficulty of each call**:

- **Mechanical, schema-shaped work** (extracting known fields into a Pydantic model, formatting a known data shape into Excel) needs a fast/cheap model — the task is close to deterministic, so a stronger model buys little.
- **Judgment calls** (the supervisor deciding whether a worker's output is actually relevant and complete before routing onward, classifying news sentiment/magnitude where nuance matters) justify a stronger model — this is where reasoning quality actually changes the outcome.

This is "model tiering," and it only works cleanly if the framework makes swapping models per-call trivial — which is one of the concrete reasons this project uses LangChain's uniform `ChatAnthropic` interface rather than hand-rolling API calls per worker.

## Other concrete levers

- **Cache upstream API responses**, not just LLM calls. A SerpApi call for the same ticker+window within a short TTL should never hit the network twice — this is a latency *and* cost lever (SerpApi is billed per search) independent of LLM spend.
- **Batch LLM calls instead of looping per-item.** Classifying 10 news articles as 10 separate structured-output calls costs ~10x the fixed overhead (system prompt, schema description) of one call that returns `list[NewsImpactScore]` for all 10 at once. Batch whenever the items are independent and the output schema supports a list.
- **Bound the pipeline.** A recursion/step limit isn't just a correctness safeguard (see `docs/04-multi-agent-orchestration.md`) — every extra supervisor loop is billed. A bug that causes 3 extra loops before hitting a limit is a cost bug, not just a correctness bug.
- **Keep worker-to-supervisor hand-offs to structured data, not full transcripts.** Passing a worker's typed Pydantic result back (a few hundred tokens) instead of its entire internal tool-calling scratchpad (potentially thousands) is both cheaper and reduces the chance the supervisor gets confused by irrelevant intermediate reasoning.
- **Track actual token usage per call, not estimates.** Every LLM response includes usage counts; capturing them in the trace (see `docs/06-agent-debugging.md`) turns "this system is probably expensive" into a real, per-run dollar figure you can act on.

## Latency vs. cost are related but distinct

A cheaper model is often also a faster model, but not always the binding constraint — network round-trips to SerpApi, and the *number* of sequential (not parallelizable) LLM calls in the critical path, matter independently. Where two tool calls don't depend on each other's output (e.g. fetching market snapshot and fetching news are independent of each other, though both depend on ticker resolution), running them concurrently is a latency win with zero cost trade-off.

---

## Our Implementation *(built and measured with real dollars — see reports/TEST_RUN_REPORT.md)*

- **Model tiers** (`.env`: `MODEL_FAST`, `MODEL_STRONG`): fast/cheap model bound to Worker C's executive-summary generation; strong model bound to the supervisor's two validation gates and Worker B's news-impact classification. **Worker A ended up using no model at all** — resolving a ticker and fetching financial data is fully deterministic tool orchestration, which turned out to be a more literal application of "match model strength to task difficulty" than originally planned (zero strength, not just low strength).
- **Caching**: `mcp_server/clients/serpapi_client.py`'s TTL cache (default 15 min, keyed by engine+params) — confirmed live that `get_stock_financials`'s two internal calls and any overlapping calls across a run's `resolve_ticker`/`get_market_snapshot` benefit from it.
- **Batched news scoring**: Worker B classifies all articles (15 in every test run) in one `.with_structured_output(NewsImpactJudgments)` call — confirmed live at ~2,200 input / ~1,000 output tokens for 15 articles in one call, versus what would have been 15 separate calls each paying the full system-prompt/schema overhead.
- **Recursion limit**: `recursion_limit=15`.
- **Token/cost tracking**: real, not estimated — `tracing/models.py` has published per-million-token pricing for both tiers, and every `llm_call`-layer `TraceEvent` records real `input_tokens`/`output_tokens` pulled from the model response's own usage metadata, aggregated by `tracing/tracer.py`'s `summarize_run_cost()`.
- **Real measured numbers** (5 live test runs, `reports/TEST_RUN_REPORT.md`): **~$0.032 per successful report**. A query that fails ticker resolution costs **$0.00** (0 LLM calls — the failure short-circuits before any model is invoked). A query that resolves to a technically-valid-but-wrong ticker and gets caught by the supervisor's semantic guardrail costs **$0.0046** (1 LLM call) rather than the full ~$0.032 pipeline. The guardrails that stop bad queries early are also what keeps them cheap — a direct, measured link between the "guardrails" and "cost" topics rather than two unrelated concerns.
- **Measured latency tradeoff**: requesting the `MAX` window (Tesla, 10-year test) took 281s wall-clock vs. ~122s for the same pipeline on a `5Y` window — a real, measured cost of a much larger price-history series inflating MCP payload size and downstream context, not a bug.
