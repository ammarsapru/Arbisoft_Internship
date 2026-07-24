# Token usage and metering

## What Waypoint currently controls

Waypoint manages token usage through hard output limits and indirect input-context
bounds.

### Hard model and loop limits

- `WAYPOINT_AGENT_MAX_OUTPUT_TOKENS`, default 6,000 and clamped to 512-32,000, limits
  the maximum generated tokens for primary agent calls.
- Assessment calls use a smaller fixed 1,800-token output limit.
- The API startup probe uses only eight maximum output tokens.
- The Claude Code health probe asks for at most 32 output tokens.
- `WAYPOINT_AGENT_MAX_TOOL_ROUNDS`, default eight, stops the outer evidence loop.
- `WAYPOINT_CLAUDE_CODE_MAX_TURNS`, default four, bounds SDK-internal turns needed to
  produce one structured Waypoint action batch.
- The Claude Code structured action schema permits at most six action calls in one
  batch.
- Final rounds force the appropriate submission tool once evidence exists, reducing
  indefinite browsing.

### Input-context controls

- Chat memory retains the most recent `WAYPOINT_CHAT_HISTORY_TURNS` user/assistant
  turns, default 12 and clamped to 1-50.
- Repository search returns at most 50 chunks to an agent request.
- `read_source` returns at most 250 lines per call.
- Tree listings, graph depth, feature candidates, entry points, related tests,
  diagnostics, and dependency impact all have explicit bounds.
- The agent receives selected chunks and tool results rather than the entire repository.
- Tool descriptions steer broad questions to high-yield semantic tools, reducing
  repeated generic search.
- Independent tools can run in one round, reducing round count even though their result
  contents still consume context.

### Work reuse that reduces repeated retrieval work

- Immutable repository revisions reuse persisted chunks and exact-content local vectors.
- SQLite FTS/vector indexes avoid rebuilding search state for every question.
- Semantic tool results are cached in process by tool name and arguments.
- Conversation history is persisted so follow-ups do not start without context.

These caches reduce compute and repeated retrieval, but Waypoint does not currently set
Anthropic `cache_control` blocks explicitly. Retrieval caching is not the same as model
prompt caching.

## What Waypoint currently meters

The Ask loop records the provider-reported `input_tokens` and `output_tokens` for each
model response in structured logs at `backend/app/agent/service.py:678-692`. Claude Code
usage is translated into the same response shape by
`backend/app/agent/provider.py:162-169`.

Logs also record:

- provider/model and round;
- message and tool counts;
- tool duration and serialized result bytes;
- inspected spans/files;
- answer citation counts;
- request failures and provider fallback.

This is operational telemetry, not complete billing metering.

## What is not implemented yet

Waypoint does not currently provide:

- a persisted per-user/per-analysis token ledger;
- cumulative token totals in the UI;
- dollar-cost calculation by provider/model;
- a hard daily/monthly monetary budget;
- per-workflow quotas or user billing;
- alerts at configured token/cost thresholds;
- complete token logging for every onboarding, assessment, mission, and issue call;
- persistence of Claude Code's `total_cost_usd` field.

Therefore it would be inaccurate to claim that Waypoint has full cost metering. It has
bounded usage and per-call Ask telemetry. Full metering should persist a usage record
containing provider, model, workflow, analysis, conversation, input/output/cache tokens,
cost, timestamp, success, and fallback reason for every model request.

## Related implementation

- `backend/app/config.py:54-62, 113-134` — model, history, round, turn, and output limits.
- `backend/app/agent/memory.py:130-205` — bounded persistent conversation history.
- `backend/app/agent/service.py:618-904` — outer rounds, forced submission, and usage logs.
- `backend/app/agent/provider.py:82-169` — six-action schema, Claude turns, and usage mapping.
- `backend/app/agent/retrieval.py:728-866` — bounded hybrid retrieval.
- `backend/app/agent/semantic.py:84-95` — semantic result cache.

