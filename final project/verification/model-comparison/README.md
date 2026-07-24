# Multi-model comparison design, matrices, and current status

## Required matrices

Waypoint evaluates three combinations. The existing Claude-only baseline remains useful, but
it does not substitute for either OpenRouter matrix.

| Matrix | Endpoint A | Endpoint B | Status |
|---|---|---|---|
| Claude + Claude baseline | Claude Code `sonnet` | Claude Code `claude-fable-5` | Completed |
| Claude + OpenRouter | Claude Code `claude-fable-5` | OpenRouter `cohere/north-mini-code:free` | Blocked by OpenRouter daily quota |
| OpenRouter + OpenRouter | OpenRouter `cohere/north-mini-code:free` | OpenRouter `nvidia/nemotron-3-super-120b-a12b:free` | Blocked by OpenRouter daily quota |

On July 24, 2026 the authenticated OpenRouter catalog confirmed both selected OpenRouter IDs:

| OpenRouter model | Catalog status | Reported context | Prompt/completion price |
|---|---|---:|---:|
| `cohere/north-mini-code:free` | Available | 256,000 tokens | 0 / 0 |
| `nvidia/nemotron-3-super-120b-a12b:free` | Available | 262,144 tokens | 0 / 0 |

The first Claude+OpenRouter execution was rejected on its first task with HTTP 429:
`free-models-per-day`, limit 50, remaining 0, reset July 25 00:00 UTC. No partial result is
labeled as a completed benchmark.

## Fair-comparison protocol

For every task, the backend performs retrieval once. It serializes the evidence with stable
key ordering, computes a SHA-256 fingerprint, and sends byte-identical evidence to both model
endpoints concurrently.

```text
task question
    ↓
one hybrid retrieval operation
    ↓
immutable evidence JSON + SHA-256
    ├── endpoint A → forced structured answer → citation validation
    └── endpoint B → forced structured answer → citation validation
```

Neither comparison model can crawl the repository. Each makes:

- **0 repository tool calls**;
- **1 structured-output submission tool call**;
- citations only within the shared frozen evidence.

This isolates model behavior from different tool choices or retrieval results. Normal Ask and
Onboarding are tested separately as agentic workflows with bounded repository tools.

## Identical task set

1. `What is this repository about? Highlight its top 10 features.`
2. `Which files are the main application entry points, and why?`
3. `How is the backend organized from HTTP entry point to business logic?`
4. `Trace one important cross-file call path and explain the evidence.`

Reference repository: Flask. Evidence limit: eight passages per task. Question limit: 500
characters. Requested output limit: `WAYPOINT_AGENT_MAX_OUTPUT_TOKENS` (default 6,000;
application range 512–32,000). Provider context limits remain separately applicable.

## Recorded metrics per task and endpoint

- provider and exact model ID;
- evidence fingerprint and evidence files;
- provider-reported input, output, and total tokens;
- end-to-end complete-response latency;
- output tokens per second;
- repository tool calls;
- structured-output tool calls;
- answer characters and citations;
- estimated cost when the provider returns it;
- schema and citation validation status;
- task wall-clock time.

### TTFT limitation

TTFT is recorded as `unavailable_non_streaming`, never inferred from total latency. The current
provider clients return complete responses. Genuine time-to-first-token requires streaming
callbacks in both provider adapters and a timestamp when the first content delta arrives.

### Claude Code token limitation

Claude Code has reported input counts as small as `2` for large serialized prompts. Those are
preserved as provider-reported/cache-adjusted usage and explicitly marked with an asterisk in
tables; they are not claimed to equal raw prompt length.

## Reproduction commands after OpenRouter quota is available

Start a dual backend for Claude+OpenRouter:

```powershell
$env:WAYPOINT_MODEL_ARCHITECTURE="dual"
$env:WAYPOINT_INVESTIGATION_PROVIDER="openrouter"
$env:WAYPOINT_INVESTIGATION_MODEL="cohere/north-mini-code:free"
$env:WAYPOINT_SYNTHESIS_PROVIDER="claude-code"
$env:WAYPOINT_SYNTHESIS_MODEL="claude-fable-5"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8012
```

Then:

```powershell
.\.venv\Scripts\python.exe -m verification.scripts.model_comparison_benchmark `
  --base-url http://127.0.0.1:8012 `
  --analysis-id YOUR_ANALYSIS_ID `
  --label claude-openrouter `
  --confirm-live-model-usage
```

For OpenRouter+OpenRouter, configure:

```powershell
$env:WAYPOINT_INVESTIGATION_PROVIDER="openrouter"
$env:WAYPOINT_INVESTIGATION_MODEL="cohere/north-mini-code:free"
$env:WAYPOINT_SYNTHESIS_PROVIDER="openrouter"
$env:WAYPOINT_SYNTHESIS_MODEL="nvidia/nemotron-3-super-120b-a12b:free"
```

and run the benchmark with `--label openrouter-openrouter`.

Expected artifacts:

- `verification/results/model-comparison-claude-openrouter.json` and `.md`;
- `verification/results/model-comparison-openrouter-openrouter.json` and `.md`.

The older `model-comparison-benchmark.*` artifacts are the Claude+Claude baseline and must be
described as such until renamed in a future artifact migration.
