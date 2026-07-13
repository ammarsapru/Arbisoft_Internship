# Connecting the `financial-analyst` MCP Server From Elsewhere

Reference commands for making this server available outside the current project-scoped Claude
Code registration.

**Status**: Command 1 (user-scope Claude Code registration) has been run and confirmed working
(2026-07-09). Command 2 (Claude Desktop) has not been run — still reference-only.

## Where does the report file land when called from elsewhere?

If you register this server at `user` scope or from Claude Desktop, it can be launched while some
*other* project is the active session — and `generate_financial_report` has no automatic way to
know that caller's working directory (an MCP tool call carries no ambient "current directory,"
only the arguments it's given). Confirmed live: without any fix, the report always landed in this
project's own `reports/` folder, regardless of which directory the calling session was in, because
the server process's own cwd is pinned by the `--directory` flag used to launch it.

Fixed by adding an `output_directory` parameter to `generate_financial_report` (and `--output-dir`
to the CLI): pass an **absolute** path and the report is written there instead. A relative path is
rejected outright (as a typed `ValidationFailure`, not a silent wrong-directory write) rather than
being resolved against the server's directory. A calling assistant that knows its own working
directory can pass it along automatically when a user asks for a report "here."

## 1. Make it available in every Claude Code project (not just this one) — DONE

```
claude mcp add financial-analyst --scope user -- uv run --directory "c:\Users\ammar\OneDrive\Desktop\personal\arbisoft\week5" python -m fin_analyst.mcp_server.server
```

To undo: `claude mcp remove financial-analyst -s user` (the project-scoped `local` registration is
independent and would be untouched).

**What it does**: registers the server at `user` scope instead of the default `local` (project)
scope, so it shows up in Claude Code sessions started from *any* directory on this machine, not
just this project folder.

**Why `--directory` is required here** (it wasn't needed for the original project-scoped
registration): `uv run` resolves the project's `pyproject.toml`/`.venv` relative to the *current
working directory* at launch time. The original command (`uv run python -m
fin_analyst.mcp_server.server`) only works because Claude Code always launches it with this
project folder as the cwd when the registration is scoped to this project. A user-scoped
registration can be launched from a session started in a completely different folder, so the
command has to tell `uv` explicitly where the project lives via `--directory`.

**Verify it worked**:
- `claude mcp list` from *any* directory should show `financial-analyst` in the list (previously
  it only appeared when run from inside this project folder).
- `claude mcp get financial-analyst` shows its registered scope and command.
- Open a new Claude Code session in an unrelated folder and confirm the server's tools
  (`resolve_ticker`, `generate_financial_report`, etc.) are available to it.

**Confirmed live** (2026-07-09): ran `cd C:\Users\ammar && claude mcp list` (an unrelated
directory, not this project) — `financial-analyst` appeared with `✔ Connected`, alongside the
`claude.ai` connectors. Also confirmed `claude mcp get financial-analyst` run *from inside this
project* still reports `Scope: Local config` — the project's own `local` registration takes
precedence over the `user`-scope one when both exist for the same name, so nothing about using it
from within this project changed.

## 2. Add it to Claude Desktop (a separate app from Claude Code)

Claude Desktop has its own config file, not shared with Claude Code:
`%APPDATA%\Claude\claude_desktop_config.json` (i.e.
`C:\Users\ammar\AppData\Roaming\Claude\claude_desktop_config.json`).

Add (or merge into) its `mcpServers` object:

```json
{
  "mcpServers": {
    "financial-analyst": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "c:\\Users\\ammar\\OneDrive\\Desktop\\personal\\arbisoft\\week5",
        "python",
        "-m",
        "fin_analyst.mcp_server.server"
      ]
    }
  }
}
```

**What it does**: tells Claude Desktop how to launch the same server as a local subprocess, same
stdio transport, same underlying code — Claude Desktop is a different application from Claude
Code but runs locally too, so nothing about the server itself changes, only which app is
launching it. If the file already has other `mcpServers` entries, this one needs to be merged in
alongside them, not overwrite the file.

**Verify it worked**:
- Fully quit and reopen Claude Desktop (it reads this config on startup, not live).
- In Claude Desktop, check Settings → Developer (or the equivalent MCP/connectors panel) — it
  should list `financial-analyst` as connected.
- Start a new chat and ask it to use one of the tools, or check that the tool icon/menu shows the
  server's tools available.

## Not covered here: Claude.ai (web)

Both commands above only work for apps running *locally on this machine*, because stdio transport
requires launching a local subprocess. Claude.ai's web chat runs in Anthropic's cloud and cannot
reach a local process — that requires converting the server to Streamable HTTP transport and
hosting it somewhere network-reachable, which is a separate piece of work not done yet (see the
"Deployment path" discussion earlier in this project's history).
