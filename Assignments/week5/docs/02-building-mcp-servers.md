# Building MCP Servers: Exposing Resources, Tools, and Prompts

## The FastMCP pattern

The official Python SDK's `FastMCP` class turns a Python function into an MCP capability via a decorator — schema generation, argument validation, and JSON-RPC wiring are handled for you from the function's type hints and docstring:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("financial-analyst")

@mcp.tool()
def resolve_ticker(company_name: str) -> ResolveTickerResult: ...

@mcp.resource("finance-report://{ticker}")
def company_report(ticker: str) -> CompanyReportBundle: ...

@mcp.prompt()
def financial_analyst_briefing(company: str) -> str: ...
```

Type hints double as the wire schema: a Pydantic return type (not a bare `dict`) means the server's own output is validated before it ever leaves the process, and a client (or another LLM) gets a real JSON Schema describing the shape of the response.

## Designing tools

A tool is a function call the model decides to make, with arguments it fills in. The two things that make a tool usable by a model (as opposed to just callable by a human who already knows what it does):

- **The docstring is the only documentation the model gets.** It has to say what the tool does, when to use it, what each parameter means, and — critically — what happens on failure/edge cases ("if the company isn't found, returns `NotPubliclyListed` rather than raising").
- **Return typed, structured results, not prose.** A `Pydantic` return model (or a discriminated union of outcome types) lets the *calling agent* branch programmatically instead of parsing a string. See `docs/08-structured-outputs-guardrails.md`.

See `docs/05-tool-design-for-agents.md` for the deeper treatment of naming, scoping, and error-message design.

## Designing resources

A resource is addressed by URI (`scheme://path`), and can be **static** (fixed URI) or a **template** (`finance-report://{ticker}` — the client fills in `{ticker}`, and the server discovers this is possible via `resources/templates/list`). Resources are meant to be cheap to read and side-effect-free — if reading it has to trigger three API calls and take 8 seconds, that's usually a sign it should be a tool instead (or that the tool's output should be cached and the resource should read the cache).

Rule of thumb used in this project: **tools fetch and compute, resources expose what's already been computed.** A tool call populates a cache entry; the resource reads that cache entry back out. This keeps resource reads fast and keeps the "when does an external API actually get hit" logic in one place (the tools).

## Designing prompts

A prompt is a template the *host* can surface directly to the user (e.g. as a slash command in Claude Code), independent of any specific tool call. It's for standardizing "how do I kick off this workflow" rather than "what data do I need right now." A prompt can reference tools/resources in its instructions but doesn't call them itself — it's static text (with parameters) returned to the client, which then decides what to do with it (usually: send it to the model as a system/user message).

## Validation at the server boundary

Every tool/resource function's input and output should be a typed Pydantic model, not a bare `dict`. This gives two things for free: (1) malformed arguments from a client are rejected before your function body runs, and (2) the JSON Schema advertised to clients is generated automatically and stays in sync with the code — no hand-maintained schema file that drifts from the implementation.

---

## Our Implementation *(built and confirmed against live SerpApi responses)*

**Tools** (`mcp_server/tools/`):

| Tool | Purpose | Notes |
|---|---|---|
| `resolve_ticker(company_name)` → `ResolveTickerResult` | Resolve a free-text company name (or an already-known `TICKER:EXCHANGE`) to a verified ticker | Live testing overturned the original design: `google_finance` **rejects plain company names outright** (no fuzzy match, no `suggestions`), so the `google` web-search engine is the primary lookup path for a free-text name, always followed by a verification call against `google_finance` before trusting the result. Returns a discriminated union (`Resolved`/`Ambiguous`/`NotPubliclyListed`/`LookupFailed`) — see `docs/08`. |
| `get_market_snapshot()` → `MarketSnapshot` | Google Finance Markets index data (US/Europe/Asia/etc.) for relative-performance comparison | No parameters — returns everything, the caller (extraction worker) picks the relevant region. |
| `get_stock_financials(ticker, exchange, company_name, window, requested_period_text, period_caveat)` → `FinancialBundle` | Summary, price graph, valuation stats, financial statements | `window` is a closed `Literal["1D","5D","1M","6M","YTD","1Y","5Y","MAX"]` (see `docs/05`). Internally makes **two** SerpApi calls, confirmed live to be necessary: a window-less call for `knowledge_graph`/`financials` and a windowed call for the price `graph` — Google Finance splits these across the two response shapes. |
| `get_company_news(ticker, company_name)` → `list[NewsArticle]` | Google News search for recent coverage | Uses the dedicated `google_news` engine, not the finance response's embedded `news_results` — confirmed live that the embedded version lacks `iso_date`, making it unusable for recency weighting. |
| `generate_financial_report(company_name, period, output_directory)` → `GenerateReportResult` | Runs the **entire** supervisor + 3-worker pipeline (extraction → news impact → Excel formatting) as one tool call | Added after initial build, once it became clear a client without direct code/filesystem access (a fresh Claude Code session, Claude.ai) has no way to trigger the LangGraph pipeline otherwise — the first four tools only expose raw data, not the orchestration or Excel-writing logic. Internally imports and calls `agents.pipeline.run_pipeline()`, which itself launches a *second* instance of this same server as a subprocess to call the four tools above — an MCP server acting as an MCP client to a freshly-spawned copy of itself. Confirmed working live (see `reports/test_generate_report_tool_raw.txt`); the only real cost is the extra subprocess startup, which is negligible next to the LLM call latency already in the pipeline. `output_directory` was added next, once a `--scope user`-registered server (launched via `uv run --directory`, pinning its own cwd) turned out to always write the report to *its own* directory regardless of where the calling session was — MCP tool calls carry no ambient "caller's cwd," so the caller has to pass it explicitly, as an absolute path (a relative one is rejected rather than silently resolving against the wrong process's directory). Confirmed live by redirecting a report to a scratch temp directory outside the project entirely (`reports/e2e_test_run_6_output_dir_raw.txt`). |
| `get_analyst_prompt(company)` → `str` | Same "expert financial analyst" framing text as the `financial_analyst_briefing` **prompt** (below), but callable as a tool | Added once it became clear the `@mcp.prompt()` primitive is surfaced by a host's UI for a *human* to pick (e.g. a slash command) and has no mechanism for the *model itself* to fetch it — so an autonomous agent had literally no way to reach that content. This tool duplicates the same text through the one primitive an agent actually can call. |

**Resources**:
- `finance-report://{ticker}` (`mcp_server/resources/report_resource.py`) — the last-cached `CompanyReportBundle`, populated as a side effect of `get_stock_financials`; the read itself makes no live API call. **Fixed bug**: this cache used to only populate when `get_stock_financials` ran as the directly-called tool — when it ran *inside* `generate_financial_report`'s internal pipeline, the pipeline's `MultiServerMCPClient` called it through a separately-spawned child server subprocess, populating *that* process's own cache, not the one serving the resource. Fixed by having `generate_financial_report` cache `state.financial_bundle` directly in the outer process once `run_pipeline()` returns, since that process already has the data in hand — independent of how many child subprocesses were involved in fetching it. Confirmed live via a single persistent session doing both the tool call and the resource read (`reports/bugfix_verification_raw.txt`); confirming this required realizing that `MultiServerMCPClient`'s convenience `get_tools()`/`.ainvoke()` API opens a fresh subprocess per call, unlike a real host's (Claude Code's) one persistent connection per session — testing through a throwaway session masked the fix at first.
- `top-companies://top20` (`mcp_server/resources/top_companies_resource.py`) — a static, hand-curated list of ~20 well-known large-cap companies and verified `ticker:exchange` pairs. Unlike `finance-report://`, this needs no prior tool call and no runtime state — it's reference data baked into the server, available from the moment it starts. Deliberately **not** presented as a live market-cap ranking: none of this project's data sources can rank companies against each other, only report stats for a ticker already in hand — the resource's own `note` field discloses this.

**Prompt**: `financial_analyst_briefing(company)` (`mcp_server/prompts/analyst_prompt.py`).

**Schemas**: two-layer raw→domain Pydantic pattern (`mcp_server/schemas/raw/` vs. `mcp_server/schemas/finance.py`/`news.py`/`report.py`) — see `plan.md`. One important lesson from getting this working: FastMCP validates a tool's *output* against pydantic's default (validation-mode) JSON Schema, which excludes `@computed_field` properties from `properties`. Combined with this project's `extra="forbid"` domain models, a `@computed_field` nested inside any MCP tool's return type fails hard with "Additional properties are not allowed" the moment it's serialized. Fixed by computing derived values (`net_margin_pct`, `outperformance_pct`) via `@model_validator(mode="after")` into ordinary stored fields instead, wherever the model crosses an MCP tool boundary.

**A second wire-format lesson**: a tool returning `list[T]` (like `get_company_news`) comes back from `langchain-mcp-adapters` as **one MCP content block per list element**, not one block containing a JSON array — confirmed by direct inspection. Code unwrapping a single-object tool result and code unwrapping a list-returning tool result need different logic (`agents/mcp_tools.py`'s `_unwrap` vs. `_unwrap_list`).
