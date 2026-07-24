# Waypoint limits and current model configuration

## Models currently used

The active `.env` uses the original single-model architecture:

```env
WAYPOINT_MODEL_ARCHITECTURE=single
WAYPOINT_MODEL=claude-sonnet-5
```

Consequently, Ask, Onboard, contribution missions, assessments, and Issues all use
Claude Sonnet 5 through the Anthropic API when that API is available.

If the API startup/runtime request fails with a recognized billing, capacity, overload,
or rate-limit error, the router falls back to the locally authenticated Claude Agent
SDK. Unless `WAYPOINT_CLAUDE_CODE_MODEL` is explicitly changed, that fallback uses the
Claude Code `sonnet` alias.

| Product workflow | Primary model | Current fallback |
|---|---|---|
| Ask | `claude-sonnet-5` through Anthropic API | Claude Agent SDK `sonnet` |
| Onboarding route | `claude-sonnet-5` through Anthropic API | Claude Agent SDK `sonnet` |
| Contribution mission | `claude-sonnet-5` through Anthropic API | Claude Agent SDK `sonnet` |
| Comprehension assessment | `claude-sonnet-5` through Anthropic API | Claude Agent SDK `sonnet` |
| Issue investigation | `claude-sonnet-5` through Anthropic API | Claude Agent SDK `sonnet` |

Fable 5 is supported but is not the currently selected fallback model. Selecting it in
single-model mode requires:

```env
WAYPOINT_CLAUDE_CODE_MODEL=claude-fable-5
```

## Dual-model architecture test status

The provider router supports both planned configurations:

1. OpenRouter investigation plus OpenRouter synthesis.
2. OpenRouter investigation plus Claude synthesis through either the Claude Agent SDK
   or Anthropic API.

Implemented automated tests verify:

- conversion of Waypoint messages and tools into OpenRouter's tool-calling format;
- conversion of OpenRouter tool responses back into Waypoint's internal format;
- routing a forced final submission to the configured synthesis provider/model;
- continued behavior of the legacy Anthropic-to-Claude-Code fallback;
- schema, citation, onboarding, and agent-loop behavior around the provider layer.

Live verification on July 23, 2026 confirmed:

- `cohere/north-mini-code:free` can produce valid forced Waypoint tool calls when given
  a realistic output allowance;
- `nvidia/nemotron-3-super-120b-a12b:free` can produce valid forced submissions;
- `claude-fable-5` is callable through the locally authenticated Claude Agent SDK;
- OpenRouter North Mini Code investigation followed by OpenRouter Nemotron 3 Super
  synthesis completed a full grounded Ask flow with validated citations;
- OpenRouter North Mini Code investigation followed by Claude Agent SDK Fable 5
  synthesis completed a full grounded Ask flow with validated citations.

The Anthropic API Fable path was probed and rejected because the configured API account
has insufficient credit. Fable is currently usable through Claude Agent SDK subscription
authentication, not through the configured Anthropic API key.

These smoke tests establish end-to-end compatibility, but they are not yet a broad
quality benchmark. Remaining work includes testing large real repositories, free-tier
rate limits and latency distributions, repeated schema reliability, provider outages,
and comparative citation/answer quality.

## Agent-loop limits

| Limit | Current value | Purpose |
|---|---:|---|
| Outer Waypoint tool rounds | 8 by current `.env` unless changed | Hard ceiling for evidence and submission rounds |
| Claude Agent SDK turns per request | 8 | Bounds internal Claude Code turns used to produce one action batch |
| Dual-mode investigation rounds | 3 by default | Switches to synthesis after evidence has been gathered |
| Synthesis attempts | 2 by default | Prevents repeated expensive final-model retries |
| Actions selected in one Claude SDK response | 6 | Allows bounded parallel read-only investigation |
| Primary model maximum output | 6,000 tokens by current `.env` | Bounds direct Messages API/OpenRouter output |
| Stored chat history sent to the model | 12 turns by current `.env` | Bounds conversational context |

`WAYPOINT_CLAUDE_CODE_MAX_BUDGET_USD`, when configured above zero, limits one
Claude Agent SDK session. It is not a cumulative budget for the entire user question
because an outer Waypoint loop can create more than one SDK session.

## Onboarding limits

Supported time budgets are:

- 5 minutes;
- 15 minutes;
- 30 minutes;
- 60 minutes;
- 90 minutes;
- 120 minutes (2 hours).

The backend accepts values from 5 through 120 minutes. The UI exposes only the intervals
listed above.

Other onboarding output limits include:

| Field | Limit |
|---|---:|
| Tour steps | 2-10 |
| Files attached to one tour step | 1-8 |
| Expected concepts for one challenge | 1-8 |
| Contribution-mission suggested files | 1-12 |
| Mission checklist entries | 2-12 |
| Definition-of-done entries | 2-12 |

## Ask citation limits

Waypoint does not restrict an answer to one citation per file. A final answer may cite
multiple distinct passages from the same file. The frontend groups those passages under
one file card and initially opens the first passage.

| Citation or answer field | Limit |
|---|---:|
| Total citations in one answer | 30 |
| Citation title | 200 characters |
| Citation relevance explanation | 500 characters |
| Full answer | 30,000 characters |
| Answer basis | 2,000 characters |
| Suggested follow-up questions | 5 |
| Displayed citation excerpt | First 8 lines and at most 1,600 characters |

There is no explicit schema-level maximum number of lines in a citation. Each citation
must have a positive start line, an end line at or after the start line, and its entire
range must be contained in evidence previously inspected by the agent.

The direct `read_source` tool returns at most 250 lines per call, which practically
bounds citations based on that tool to its inspected range. Specialized semantic and
graph tools commonly return smaller evidence spans.

## Ask composer behavior

When a question is submitted:

1. The composer is cleared immediately.
2. The user message is inserted into the conversation immediately.
3. A loading state is shown while the request runs.
4. The assistant response fills the pending conversation turn when it arrives.
5. If the request fails, the submitted user message remains visible with an error.

## Verification status

The most recent local verification completed successfully:

- frontend TypeScript and production Vite build;
- 68 backend tests;
- OpenRouter translation and dual-role routing unit tests;
- live OpenRouter-to-OpenRouter grounded Ask smoke test;
- live OpenRouter-to-Fable grounded Ask smoke test;
- two-hour onboarding validation.

This verification includes live provider smoke tests but not a large-repository
benchmark suite.
