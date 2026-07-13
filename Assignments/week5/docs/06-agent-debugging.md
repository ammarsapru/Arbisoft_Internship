# Agent Debugging: Tracing Tool Calls, Replaying Transcripts, Isolating Failures

## Why agent systems are harder to debug than normal programs

A normal stack trace shows you one deterministic call path. An agent system's "call path" is chosen at runtime by a model, differs between runs of the *same* input due to model non-determinism, and spans multiple processes (agent process, MCP server process, external APIs) — so a bug can be "the model chose badly," "the tool did the wrong thing," "the API returned something unexpected," or "the validation gate let bad data through," and these look identical from the outside (wrong final answer) unless you have visibility into every intermediate step.

## Tracing: the minimum viable observability

The floor for debuggability is: **every tool call and every agent/node transition gets logged as a structured event**, with enough detail to answer "what was called, with what arguments, what came back, how long did it take, did it succeed." This needs to span *both* layers of this project — the MCP server's tool calls and the LangGraph agent's node/tool invocations — under one unified, correlatable identifier (a run ID), because a bug can originate in either layer and you need to see the full sequence to tell which.

Industry-standard tracing increasingly follows **OpenTelemetry's GenAI semantic conventions** (spans for LLM calls, tool invocations, agent steps, with attributes for token counts and cost) exported to a backend like Jaeger or an APM tool. For a project at this scale, a lightweight custom tracer that captures the same *shape* of information (structured events, not raw print statements) to a local JSONL file gets the same debugging value without standing up collector infrastructure — see `docs/07-cost-latency-strategy.md` for how the same trace events double as the cost-accounting data source.

## Replaying transcripts

A trace file that's just a flat log is only half useful — the other half is a **replay tool** that reconstructs a readable timeline from it: which agent ran, which tools it called in what order, what each call's input/output was, and where in that sequence things went wrong. This turns "the report was wrong" into "Worker B's news query returned zero articles for this ticker, so the impact score defaulted to neutral" — a concrete, fixable finding instead of a guess.

## Isolating failures: which layer is broken?

A systematic way to narrow down a failure, from outside in:

1. **Is the MCP server correct on its own?** Call the tool directly (via Claude Code, or a unit test with a fixture SerpApi response) — if the tool itself returns wrong/malformed data independent of any agent, the bug is server-side (parsing, mapping raw→domain, or the upstream API itself).
2. **Is the agent choosing the right tool with the right arguments?** Check the trace for the tool-call event: correct tool name, sane arguments. If not, the bug is in the agent's prompt or the tool's description being unclear/misleading — a tool-design problem, not an implementation bug (see `docs/05-tool-design-for-agents.md`).
3. **Is the validation gate catching what it should?** Check whether a `ValidationFailure` was recorded and whether the supervisor reacted to it correctly. A gate that never fires is either doing nothing (bug) or the upstream data really is always valid (no bug, but worth a synthetic bad-input test to confirm the gate actually works).
4. **Is the final synthesis (LLM narrative / Excel output) faithful to the validated data?** If everything upstream is correct but the final output is wrong, the bug is in the last-mile formatting/prompting step.

Having typed, structured intermediate state (per `docs/08-structured-outputs-guardrails.md`) is what makes step 1–3 possible at all — you can't isolate "the data was right but the narrative was wrong" if the data was never captured in a structured, inspectable form in the first place.

---

## Our Implementation *(built and used to debug the project's own real bugs)*

- **`TraceEvent`** (Pydantic, `tracing/models.py`): `run_id`, `timestamp`, `layer` (`"mcp_tool" | "agent_node" | "llm_call"`), `actor`, input/output previews, `latency_ms`, `status`, `error_detail`, plus token-usage fields on LLM-layer events (see `docs/07`).
- **Capture points**: `tracing/mcp_middleware.py` wraps every `@mcp.tool()` function server-side; `tracing/callbacks.py`'s `TracingCallbackHandler` (a LangChain `BaseCallbackHandler`) is passed into the graph's `ainvoke(..., config={"callbacks": [...]})`, capturing `on_llm_start/end` cleanly (model name, real token counts) and `on_chain_start/end`/`on_tool_start/end` at a coarser grain — LangGraph's internal node wrapping surfaces as generically-named "chain" spans rather than the specific node name, a known limitation noted honestly rather than glossed over; the MCP-tool and LLM layers carry clean, specific names and are where the real debugging value is.
- **`tracing/replay.py`**: `uv run python -m fin_analyst.tracing.replay <run_id>` prints a chronological table (offset, layer, actor, status, latency, tokens) plus a run summary. This tool is what actually diagnosed several of this project's own real bugs during testing (see `reports/TEST_RUN_REPORT.md`'s "Bugs found and fixed" section) — e.g. confirming a run stopped after exactly 1 MCP tool call and 0 LLM calls was the fast, cheap "not publicly listed" short-circuit working as intended, not a crash.
- **Process-boundary correlation**: since the MCP server runs as a subprocess of the agent process, `run_id` is propagated via a `TRACE_RUN_ID` environment variable at subprocess launch (`agents/mcp_client.py`) rather than relying on an in-process-only contextvar — confirmed live that `mcp_tool` and `llm_call` events for the same pipeline run land in the same `traces/<run_id>.jsonl` file.
- Every test run in `reports/TEST_RUN_REPORT.md` cites its `run_id` so any claimed result can be independently replayed rather than taken on faith.
