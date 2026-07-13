# Model Context Protocol (MCP): Fundamentals, Transport, Capabilities

## What problem MCP solves

Before MCP, every LLM application that wanted to call external tools or pull in external data invented its own integration format: a bespoke function-calling schema, a bespoke way of injecting context, a bespoke auth story. Every new data source meant N-times integration work (once per app) and every new app meant M-times integration work (once per data source). MCP is a standard protocol that turns this into an N+M problem: a data/tool provider implements one MCP **server**, and any MCP-compatible **client** (Claude Code, Claude Desktop, Cursor, a custom app) can talk to it without bespoke glue code.

It is deliberately modeled on **Language Server Protocol (LSP)** — the same idea that let every editor support every language without a combinatorial explosion of plugins, applied to "every AI app supports every tool/data source."

## Core architecture

- **Host**: the end-user-facing application (Claude Code, Claude Desktop, a custom agent app). The host embeds one or more MCP clients.
- **Client**: a 1:1 connection manager between the host and a single MCP server. If a host talks to 3 servers, it holds 3 client instances.
- **Server**: a process that exposes capabilities (resources, tools, prompts) over the protocol. A server doesn't know or care which host is talking to it.

Communication is JSON-RPC 2.0 over a transport. The protocol is session-based: client and server perform a capability-negotiation handshake (`initialize` / `initialized`) before any real work happens, so each side only advertises/uses features the other actually supports.

## Transports

| Transport | How it works | When to use |
|---|---|---|
| **stdio** | Server runs as a child process; JSON-RPC messages go over its stdin/stdout | Local tools, CLI-launched servers (Claude Code's default for locally-run servers). Simplest to build and debug — no networking, no auth to think about. |
| **Streamable HTTP** (current spec) | Server is a long-running HTTP endpoint; client POSTs JSON-RPC requests and can receive an SSE stream back for server-initiated messages/streaming responses | Remote/shared servers, servers that need to be reachable by multiple hosts or over a network, servers that need to scale independently of any one client process. |
| **SSE (legacy)** | Predecessor to Streamable HTTP — separate SSE stream + HTTP POST endpoint | Being phased out in favor of Streamable HTTP; only relevant for compatibility with older servers/clients. |

Local, single-user tools (like this project's server during development) default to stdio: zero network config, and Claude Code launches/kills the process for you.

## Capabilities: the three primitives

MCP servers expose functionality through three primitive types, and the mental model for telling them apart matters:

- **Resources** — read-only, URI-addressable data (think `GET` endpoints). A resource is something the *host* decides to pull into context — the model doesn't "call" a resource the way it calls a tool; the client/host fetches it and injects it. Good for: reference data, current state, things useful to have in context without an explicit request every time.
- **Tools** — invocable functions with side effects or computation (think `POST` endpoints). A tool is something the *model* decides to call, with arguments, expecting a result back. Good for: fetching live data on demand, performing an action, anything that needs specific parameters per-call.
- **Prompts** — reusable, parameterized message templates the host can surface (e.g. as a slash command). Good for: standardizing a way of kicking off a common workflow ("act as X and do Y for {param}") without every user having to hand-write the same instructions.

Capability negotiation means a server declares which of these three it supports during `initialize`, and a minimal server can implement just one (e.g. tools only).

## Why this matters for a multi-agent system

In a supervisor/worker agent system, the MCP server is the seam between "how do I get real-world data" and "how do agents reason about it." Keeping that seam protocol-standard (rather than a bespoke internal API) means the same server can be smoke-tested manually from Claude Code before any agent code exists — which is exactly how this project's build order is sequenced (server first, agents second).

---

## Our Implementation *(built and tested against live SerpApi + Claude Code)*

- **Transport**: stdio, registered with Claude Code via `claude mcp add financial-analyst -- uv run python -m fin_analyst.mcp_server.server`. The agent-side `MultiServerMCPClient` (`agents/mcp_client.py`) launches the identical server as a subprocess over the same stdio transport — confirmed live that both paths hit the exact same tool implementations with no server-side changes needed.
- **Server framework**: the official `mcp` Python SDK's `FastMCP` app (`mcp_server/server.py`).
- **Capabilities exposed** (all confirmed working end-to-end, see `reports/TEST_RUN_REPORT.md`):
  - Resource: `finance-report://{ticker}` — the cached `CompanyReportBundle` populated by the last `get_stock_financials` call in the server's process lifetime.
  - Tools: `resolve_ticker`, `get_market_snapshot`, `get_stock_financials`, `get_company_news`, plus `generate_financial_report` — a fifth tool that runs the entire supervisor+worker pipeline as one call, added once it was clear the first four only expose data, not orchestration (see `docs/02`).
  - Prompt: `financial_analyst_briefing`.
- **One process-boundary detail worth noting here**: because the agent's `MultiServerMCPClient` launches the server as a *subprocess*, tracing the two together required explicitly propagating a `run_id` across that boundary via a `TRACE_RUN_ID` environment variable set at subprocess launch (`agents/mcp_client.py`) — a contextvar alone (used within each process) doesn't cross a process boundary. See `docs/06-agent-debugging.md`.
- Tool/resource/prompt schema details and the SerpApi field-shape discoveries live in `docs/02-building-mcp-servers.md` and `plan.md`.
