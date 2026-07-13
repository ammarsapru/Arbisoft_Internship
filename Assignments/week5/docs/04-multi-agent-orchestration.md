# Multi-Agent Orchestration: Supervisor + Worker Patterns, Hand-offs

## Why split into multiple agents at all

A single agent with a huge system prompt and every tool available tends to degrade as scope grows: it forgets instructions relevant to a task type it isn't currently doing, its tool selection gets noisier the more tools are in context, and a single conversation transcript conflates unrelated reasoning (financial extraction logic mixed with Excel-formatting logic mixed with news-sentiment reasoning). Splitting into focused sub-agents — each with a narrow prompt, a narrow toolset, and a typed contract for what it returns — keeps each agent's context small and its failure modes легible.

## Supervisor vs. swarm

Two dominant patterns for connecting multiple agents:

- **Supervisor (hierarchical)**: a central orchestrator agent owns routing. It decides which worker runs next, passes it the relevant slice of state, receives a structured result back, and decides what happens next (another worker, a retry, done). Workers never talk to each other directly or to the end user — control always returns to the supervisor.
- **Swarm (peer hand-off)**: agents hand off control to each other directly, dynamically, without a central router — closer to a relay race than a hub-and-spoke.

The supervisor pattern is more accurate (routing is the supervisor's *only* job, so it's a small, focused decision each time) at the cost of an extra LLM call per hand-off (latency). Swarm is faster but more prone to misrouting since routing logic is diffused across every agent instead of centralized. **Start with supervisor** — it's simpler to build and debug, and routing-accuracy matters more than the latency cost for most early systems; only move to swarm once you have data showing latency, not misrouting, is the actual bottleneck.

## Hand-offs

A hand-off is the moment control (and usually a slice of state/context) passes from one agent to another. In a LangGraph supervisor graph this is implemented as **routing**: the supervisor node's output determines which node the graph transitions to next (a conditional edge), and the state object carries forward whatever the next worker needs — it does not need the full conversation history, just the typed fields relevant to its job.

Two hand-off mechanics worth distinguishing:
- **Full hand-off** (swarm-style): the receiving agent gets the entire conversation transcript and effectively "becomes" the active agent for the user.
- **Delegated call** (supervisor-style, used here): the supervisor calls a worker like a function — passing specific inputs, getting a specific typed output back — and remains in control throughout. The worker's internal reasoning (its own tool calls, its own scratch thinking) never leaks into the supervisor's context; only its final structured result does.

## Termination and validation gates

A supervisor graph needs an explicit stopping condition, or it can loop. The clean pattern: the supervisor's prompt says "when the task is fully addressed, produce the final answer and stop," and each worker call is followed by a **validation gate** — a check (schema validation at minimum, a relevance/quality check at best) before the supervisor is allowed to route onward. This also bounds runaway loops: a sane recursion/step limit (a four-specialist pipeline realistically takes 6–10 steps) catches a broken routing prompt before it burns unbounded tokens.

## Where this project's pattern differs from a chat-style agent

None of the three workers here talk to the end user directly, and none of them make user-facing judgment calls about *whether* to continue — that authority stays entirely with the supervisor. This mirrors a batch-pipeline shape (extract → analyze → format) more than a conversational hand-off shape, which is exactly why the supervisor pattern (not swarm) fits.

---

## Our Implementation *(built and tested — see reports/TEST_RUN_REPORT.md)*

- **Framework**: LangGraph `StateGraph` (`agents/graph.py`), hand-built rather than the `langgraph_supervisor` prebuilt helper, so each worker→supervisor transition carries an explicit validation gate (`agents/supervisor.py`) rather than a generic routing decision.
- **Graph shape**: `extraction → validate_extraction → news_impact → validate_news → formatting → validate_formatting → END`, with every `validate_*` node able to short-circuit straight to `END` via `next_step="aborted"`. Confirmed live in two separate test runs: a nonexistent company aborted after extraction with **zero LLM calls** (the ticker-resolution failure short-circuits before the supervisor's LLM gate even runs), and a low-confidence "SpaceX" resolution passed its deterministic ticker verification but was correctly caught and aborted by the supervisor's *semantic* LLM check — a concrete example of the deterministic and semantic guardrail layers catching different classes of error.
- **State**: `PipelineState` (Pydantic, `agents/state.py`) carries `company_query`, `period_query`, each worker's typed bundle once produced (`ticker_result`, `financial_bundle`, `news_impact_bundle`, `report_output`), and `validation_failures: Annotated[list[ValidationFailure], operator.add]` so failures accumulate across stages via LangGraph's reducer mechanism rather than overwrite.
- **Worker A makes zero LLM calls** — resolving a ticker and fetching financial data is fully deterministic tool orchestration once the company query is known, so no model is bound to that node at all. This ended up being a stronger example of "match model strength to task difficulty" (`docs/07`) than originally planned: not just a cheap model, but no model.
- **Recursion limit**: `recursion_limit=15`, passed via the `ainvoke` config alongside the tracing callback handler.
