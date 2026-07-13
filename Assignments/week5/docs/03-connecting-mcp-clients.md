# Connecting MCP Clients to Existing Apps (Claude Code, Cursor, Custom)

## What a client actually does

An MCP client is the connection-manager half of the host↔server relationship: it launches/connects to a server, performs the `initialize` handshake, discovers what capabilities the server offers (`tools/list`, `resources/list`, `prompts/list`), and translates the host's needs into JSON-RPC calls (`tools/call`, `resources/read`, `prompts/get`). Every MCP-compatible host bundles its own client implementation, but they all speak the same protocol to the server — which is the entire point.

## Claude Code as a client

Claude Code can register a server via `claude mcp add <name> -- <command>` (stdio) or with a URL (HTTP). Once registered, the server's tools show up alongside Claude Code's built-in tools, its resources can be attached to context, and its prompts show up as invokable templates. This is the fastest way to manually exercise a server during development — no custom client code needed, and you get a real UI for approving/denying tool calls, which doubles as a sanity check that your tool descriptions make sense to a model.

## Cursor / other IDE hosts

Same idea, different config surface (typically a `mcp.json` pointing at the same stdio command or HTTP URL). Because the protocol is standard, a server built and tested against Claude Code needs zero changes to also work in Cursor — only the host-side registration differs.

## Custom clients (the case that matters most for this project)

When an MCP server needs to be called from your *own* application code — not from an interactive chat host — you write a custom client. In a Python LangChain/LangGraph app, the standard tool for this is **`langchain-mcp-adapters`**: it wraps the low-level `mcp` client session and converts every tool the server exposes into a LangChain `StructuredTool` (with the tool's JSON Schema becoming a Pydantic `args_schema`), so agent code calls MCP tools exactly like any other LangChain tool — no hand-written JSON-RPC.

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "financial-analyst": {
        "command": "python",
        "args": ["-m", "src.mcp_server.server"],
        "transport": "stdio",
    }
})
tools = await client.get_tools()   # list[StructuredTool], ready for a LangGraph agent
```

`MultiServerMCPClient` also supports connecting to *multiple* servers at once and merging their tools into one list — relevant if this project ever grows a second MCP server (e.g. a separate SEC-filings server) without changing how the agent graph consumes tools.

## Why this project uses both

Testing via Claude Code and testing via a custom client answer different questions: Claude Code confirms the server itself is correct (schemas, error messages, whether a human-in-the-loop reviewer finds the tool descriptions clear) independent of any agent logic. The custom client confirms the *agent* correctly discovers and invokes those same tools programmatically. Building the server against Claude Code first, then pointing the same server at a custom client, means a bug can always be isolated to one layer or the other.

---

## Our Implementation *(built and confirmed working)*

- **Manual/dev client**: Claude Code, registered via `claude mcp add financial-analyst -- uv run python -m fin_analyst.mcp_server.server`. Used to manually invoke tools and eyeball responses against the Pydantic schemas independent of any agent code.
- **Programmatic client**: `agents/mcp_client.py` — `MultiServerMCPClient` pointed at the same stdio-launched server (`sys.executable -m fin_analyst.mcp_server.server`), with `TRACE_RUN_ID` injected into the subprocess environment so its trace events land in the same run as the calling agent's (see `docs/06-agent-debugging.md`). `client.get_tools()` returns LangChain `StructuredTool`s bound directly to the workers via `agents/mcp_tools.py`.
- **A confirmed detail worth knowing before writing client-side unwrap code**: the tool results returned by `StructuredTool.ainvoke()` are MCP content blocks (`[{"type": "text", "text": "<json>"}]`), and a tool returning a single Pydantic object comes back as one block, while a tool returning `list[T]` comes back as one block *per element* — `agents/mcp_tools.py` has separate `_unwrap`/`_unwrap_list` helpers for the two cases, discovered by directly inspecting a live tool call's raw return value rather than assuming a shape.
- Both clients talk to the *same* server process definition — confirmed nothing server-side changed between manual Claude Code use and the programmatic pipeline runs in `reports/TEST_RUN_REPORT.md`.
