# Waypoint AI-assisted engineering prompt log

This is the maintained record of significant AI-assisted development. It records what was
asked, the constraints given to the coding agent, what was accepted or corrected by the
developer, the resulting implementation, and how it was verified. It is not a transcript of
every explanatory question. Prompts the developer explicitly excluded are not reproduced.

Entries before this log existed were reconstructed from the implementation history and are
therefore labeled **reconstructed**. No API keys, login tokens, private chain-of-thought, or
repository source contents are recorded here.

## 1. Graph foundation and maximum observability — reconstructed

**Development prompt**

> Build the first practical phase of an adaptive codebase-onboarding application. Analyze a
> repository statically, return modules, symbols, relationships, unresolved references, and
> diagnostics over FastAPI. Add extremely descriptive terminal output for every process,
> subprocess, function entry, function exit, returned result, duration, and error so a failure
> can be located precisely. Do not execute analyzed repository code, and constrain paths to a
> configured allowed root.

**Important constraints and decisions**

- Repository paths must be resolved and checked as descendants of `ONBOARD_ALLOWED_ROOT`.
- Graph evidence must distinguish verified syntax, conservative inference, and unresolved
  behavior; static guesses cannot be represented as certainty.
- Function tracing must redact secrets and bound logged values rather than dumping unlimited
  source or credentials.
- Git subprocesses must be non-interactive, timed, and logged with exit status and duration.

**AI-produced implementation reviewed by the developer**

- Typed Pydantic graph models for repositories, modules, classes, functions, methods, edges,
  evidence, diagnostics, and analysis statistics.
- Python AST discovery, definition extraction, import/call relationships, and stable IDs.
- FastAPI analysis, graph-summary, source, and neighborhood endpoints.
- Structured `log_event` records, `@traced` pre/post/error hooks, trace correlation IDs,
  rotating JSONL output, subprocess stream capture, and maximum call tracing.

**Developer corrections**

- Clarified that `relative_to` is a containment test, not a way to change the allowed root.
- Required `may_call` to remain explicitly inferred and visible by default.
- Required affirmative dispatch logs only after the path-boundary check succeeds.

**Validation evidence**

- `backend/tests/test_analyzer.py`
- `backend/tests/test_api.py`
- `backend/tests/test_observability.py`
- `backend/tests/test_repository_import.py`

## 2. Interactive graph, file cards, and onboarding UX — reconstructed

**Development prompt**

> Build a modern React, TypeScript, Tailwind UI with light and dark modes. Preserve selectable
> graph node types, but add file cards that contain their classes, functions, and methods.
> Connect files based on real imports, calls, and instantiations. Make the repository and
> inspector sidebars collapsible, make the source viewer vertically draggable, and make
> fullscreen graph mode work. Onboarding must respond to role, experience, objective, and time
> budget rather than return a fixed route.

**Implementation**

- React Flow symbol and file-card presentations with evidence-aware edges.
- Repository tree, inspector tabs, source viewer, draggable split, fullscreen controls, and
  persistent theme/workspace preferences.
- Role-specific tours, mastery questions, contribution missions, and source evidence.
- Ask split view: chat on the left and only cited evidence files on the right.

**Developer corrections**

- File cards remained additive; symbol-level exploration was not removed.
- Ask evidence had to be clickable and synchronized with the source panel.
- The input clears immediately after submission while the user message remains in chat.
- Conversation memory had to survive refreshes through SQLite, not only component state.

**Validation evidence**

- `frontend/e2e/application.spec.ts`
- `frontend/e2e/voicebox.acceptance.spec.ts`
- `backend/tests/test_onboarding.py`
- frontend TypeScript and production builds

## 3. Secure GitHub import — reconstructed

**Development prompt**

> Let the user choose a local path or public GitHub repository in the UI. For GitHub, clone the
> repository into an application-controlled folder and analyze that checkout. Prevent local
> transports, embedded credentials, path traversal, interactive Git prompts, unbounded clones,
> and accidental execution of repository code.

**Implementation and limits**

- Accepts public `github.com/owner/repository` HTTPS identities.
- Shallow, non-interactive clone into `.waypoint-clones` with normalized generated names.
- Checkout file-count, byte-size, timeout, and retained-clone limits.
- Clone folder remains under the configured allowed root and is excluded when analyzing its
  parent workspace.
- GitHub identity is retained for issue-history retrieval.

**Validation evidence**

- URL and transport rejection cases in `backend/tests/test_repository_import.py`.
- HTTP GitHub-import route contracts in `backend/tests/test_api.py`.
- Flask and Django external-repository benchmark artifacts.

## 4. Polyglot static analysis — reconstructed and extended July 24, 2026

**Development prompt**

> Extend the shared graph schema beyond Python to JavaScript, JSX, TypeScript, TSX, and Java.
> Detect files, definitions, imports, calls, constructed classes, and cross-file member usage.
> Keep unresolved dynamic behavior visible. Later, add HTML and CSS as first-class analyzed
> files with local asset relationships and selectable declarative symbols.

**Implementation**

- Dedicated Tree-sitter grammars for JavaScript, TypeScript/TSX, Java, HTML, and CSS.
- ES imports/re-exports, CommonJS aliases, Java packages/imports, receiver types,
  instantiations, and conservatively recovered calls.
- HTML IDs/classes and CSS selectors become source-backed symbols within their file cards.
- Local HTML `src`/`href` and CSS `@import` references become verified file edges; external
  web assets remain explicitly unresolved external dependencies.
- All supported files participate in snapshot fingerprints, chunk retrieval, source viewing,
  and automatic index refresh.

**Static-analysis boundaries**

- Runtime reflection, framework injection, generated code, browser DOM mutation, CSS
  preprocessors, bundler aliases, and TypeScript project-reference semantics are not inferred
  without dedicated configuration or runtime evidence.

**Validation evidence**

- `backend/tests/test_polyglot_analyzer.py`
- mixed-language file-count, parser-recovery, import, call, and instantiation assertions

## 5. Agentic graph RAG, tools, and memory — reconstructed

**Development prompt**

> Replace predetermined repository answers with an agent that can answer arbitrary questions
> from repository evidence. Give it precise bounded tools rather than the entire codebase.
> Store conversations, retain the past N turns, cite only evidence actually inspected, and
> allow symbol-scoped Ask inside the inspector. Use graph structure and an index to retrieve
> efficiently and keep chunks current when repository files change.

**Architecture produced**

- Deterministic repository-overview, feature, entry-point, backend-layer, structure, symbol,
  related-test, impact, configuration, diagnostics, source-read, search, and graph tools.
- Persistent SQLite revisions with file hashes, symbols, edges, chunks, FTS5/BM25, local
  subword vectors, rank fusion, and graph expansion.
- Content fingerprint comparison triggers graph/index rebuilds after source changes.
- Bounded multi-round investigation followed by structured answer submission.
- Citation validation rejects invented files and ranges; narrowly bounded recovery reads real
  source ranges the synthesizer identifies.
- SQLite conversations restore Ask and onboarding context across refreshes.

**Developer corrections**

- The answer evidence panel must show only files the final response used.
- Repository-overview questions prioritize README/manifests/production entry points rather
  than treating test names as product features.
- Agent-round exhaustion must report provider/round limits clearly and permit configured
  eight-round investigation.

**Validation evidence**

- `backend/tests/test_agent.py`
- `backend/tests/test_semantic_tools.py`
- `backend/tests/test_questions.py`
- retrieval benchmark cases and live Flask workflow

## 6. MCP connector and execution hooks — reconstructed

**Development prompt**

> Expose existing Waypoint services as an MCP server and install pre-call, post-call, and
> exception hooks across service boundaries. Log tool name, bounded arguments, result shape,
> bytes, duration, model/provider, rounds, tokens, cost when available, and correlation IDs.
> Make output readable, but do not claim access to hidden model thoughts.

**Implementation**

- MCP server over stdio and Streamable HTTP with 17 bounded tools plus resources/prompts.
- MCP calls reuse the same path, source-range, graph, index, clone, and validation limits as
  HTTP calls.
- Function, HTTP, process, subprocess, model, agent-round, tool, retrieval, and validation
  events share trace context.
- Sensitive fields are redacted and large values are summarized/truncated.

**What the logs prove**

They prove the observable execution path: prompts sent, models selected, tools requested,
tool inputs/results, validations, timings, token reports, exceptions, and final structured
outputs. They do not reveal private chain-of-thought.

**Validation evidence**

- `backend/tests/test_mcp_server.py`
- `backend/tests/test_observability.py`
- `waypoint-mcp.example.json`
- focused live trace in `verification/results/live-multistep-trace.jsonl`

## 7. Multi-provider/model routing and comparison — reconstructed and extended July 24, 2026

**Development prompt**

> Support either two OpenRouter models split by task or OpenRouter plus Claude through the
> Anthropic API/locally authenticated Claude Agent SDK. Probe providers, fall back on billing
> failures, meter usage, and bound model turns. Also provide a fair comparison where the same
> task and byte-identical evidence are sent to two models and report quality evidence, latency,
> input/output tokens, cost, tool calls, output size, and TTFT when genuinely observable.

**Implementation**

- Explicit investigation and synthesis provider/model endpoints.
- OpenRouter, Anthropic API, and Claude Agent SDK adapters with startup probes and fallbacks.
- Role routing for normal agent operation and parallel frozen-evidence fan-out for comparison.
- SHA-256 evidence fingerprint, independent schema/citation validation, latency, provider
  token reports, output size, tool count, requested output cap, and cost fields.
- Multi-task benchmark runner writes JSON plus readable Markdown tables.

**Measurement correction**

The comparison endpoint is currently non-streaming. Full response latency is measured, but
TTFT is recorded as unavailable rather than incorrectly relabeling total latency. True TTFT
requires provider streaming callbacks. Claude Code usage can also report cache-adjusted or
very small input-token counts; the report preserves the provider value and documents that
limitation.

**Validation evidence**

- `backend/tests/test_provider.py`
- `backend/tests/test_model_comparison.py`
- `verification/scripts/model_comparison_benchmark.py`
- `verification/results/live-multistep-report.json`

## 8. Verification, session recovery, and deployment — July 24, 2026

**Development prompt**

> Establish a failing 70% coverage threshold and comprehensive unit, integration, browser,
> and real HTTP E2E evidence against a known moderate repository. Convert coverage XML into a
> readable report. Demonstrate a live multi-step agent with hooks and logs. Let users reopen
> any retained analyzed repository session. Repair the disconnected landing diagram. Package
> reproducible deployment for a Vercel frontend plus persistent backend or Docker Compose.

**Implementation**

- `pytest-cov` branch-aware 70% gate with terminal, Cobertura XML, and annotated HTML output.
- XML-to-Markdown coverage converter and human-readable lowest-coverage table.
- Deterministic Flask HTTP E2E plus opt-in live model workflow.
- Restart-safe recent-analysis endpoint and UI selector retaining up to 50 sessions.
- Four visible landing graph edges connecting all five demonstration cards.
- Separate backend/frontend Dockerfiles, Nginx API proxy, persistent volumes, and Compose.
- Configurable `VITE_API_BASE_URL` for a Vercel frontend talking to a hosted backend.

**Validation expected for every release**

```powershell
.\.venv\Scripts\python.exe -m pytest
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m verification.scripts.coverage_report
docker compose config
```

Live model and external-repository runs stay opt-in because they consume provider quota and
network resources.
