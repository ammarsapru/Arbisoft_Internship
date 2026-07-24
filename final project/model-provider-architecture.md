# Two-role model architecture

Waypoint can run in its original single-provider mode or split model work into two
roles:

1. The **investigation model** selects repository tools, searches the index, reads
   bounded source ranges, and expands graph relationships.
2. The **synthesis model** receives the accumulated inspected evidence and must submit
   the final typed, source-cited response.

The backend, not either model, executes tools and validates every citation.

## Option A: two free OpenRouter models

```env
OPENROUTER_API_KEY=your-key
WAYPOINT_MODEL_ARCHITECTURE=dual
WAYPOINT_INVESTIGATION_PROVIDER=openrouter
WAYPOINT_INVESTIGATION_MODEL=cohere/north-mini-code:free
WAYPOINT_SYNTHESIS_PROVIDER=openrouter
WAYPOINT_SYNTHESIS_MODEL=nvidia/nemotron-3-super-120b-a12b:free
WAYPOINT_INVESTIGATION_ROUNDS=3
WAYPOINT_SYNTHESIS_MAX_ATTEMPTS=2
WAYPOINT_AGENT_MAX_TOOL_ROUNDS=6
```

Free model identifiers and availability change. Pinning models makes behavior easier to
test than `openrouter/free`; update an unavailable identifier through `.env` without a
code change. This exact pair passed a live forced-tool probe and a complete grounded Ask
flow on July 23, 2026.

## Option B: OpenRouter investigation plus Claude synthesis

```env
OPENROUTER_API_KEY=your-key
WAYPOINT_MODEL_ARCHITECTURE=dual
WAYPOINT_INVESTIGATION_PROVIDER=openrouter
WAYPOINT_INVESTIGATION_MODEL=cohere/north-mini-code:free
WAYPOINT_SYNTHESIS_PROVIDER=claude-code
WAYPOINT_SYNTHESIS_MODEL=claude-fable-5
WAYPOINT_INVESTIGATION_ROUNDS=3
WAYPOINT_SYNTHESIS_MAX_ATTEMPTS=2
WAYPOINT_AGENT_MAX_TOOL_ROUNDS=6
WAYPOINT_CLAUDE_CODE_MAX_TURNS=2
WAYPOINT_CLAUDE_CODE_MAX_BUDGET_USD=0.35
```

`claude-code` uses the account already authenticated by the local Claude Code CLI. It
does not read `ANTHROPIC_API_KEY`. This mode is suitable for local personal development,
not for sharing one developer's subscription credentials with application users.
This exact OpenRouter-to-Fable path passed a live forced-tool probe and a complete
grounded Ask flow on July 23, 2026.

To use Fable through the paid Anthropic API instead:

```env
ANTHROPIC_API_KEY=your-key
WAYPOINT_SYNTHESIS_PROVIDER=anthropic-api
WAYPOINT_SYNTHESIS_MODEL=claude-fable-5
```

## Limits and behavior

- `WAYPOINT_INVESTIGATION_ROUNDS` controls when the Ask agent switches to forced
  synthesis once it has inspected evidence.
- `WAYPOINT_AGENT_MAX_TOOL_ROUNDS` remains the hard outer-loop ceiling.
- `WAYPOINT_SYNTHESIS_MAX_ATTEMPTS` prevents repeated expensive final-model retries.
- `WAYPOINT_CLAUDE_CODE_MAX_TURNS` limits internal SDK turns for one model request.
- `WAYPOINT_CLAUDE_CODE_MAX_BUDGET_USD` limits one Claude Agent SDK session. It is not a
  cumulative per-question ledger because each outer round is a separate SDK session.
- The final answer still passes Pydantic validation and must cite source spans returned
  by retrieval tools.
- Structured logs include `model.role_routed`, the selected provider/model, token usage,
  and provider-reported estimated cost when available.

Restart the backend after changing provider environment variables because settings are
loaded at process import time.
