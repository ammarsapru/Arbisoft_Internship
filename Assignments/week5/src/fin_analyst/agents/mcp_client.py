import os
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient


def build_mcp_client(run_id: str) -> MultiServerMCPClient:
    """Launches the financial-analyst MCP server as a stdio subprocess and
    wraps it as a LangChain-compatible tool source. TRACE_RUN_ID is injected
    into the subprocess environment so its tool-call trace events land in
    the same JSONL file as this run's agent-layer events - see
    docs/03-connecting-mcp-clients.md and docs/06-agent-debugging.md."""
    env = dict(os.environ)
    env["TRACE_RUN_ID"] = run_id

    return MultiServerMCPClient(
        {
            "financial-analyst": {
                "command": sys.executable,
                "args": ["-m", "fin_analyst.mcp_server.server"],
                "transport": "stdio",
                "env": env,
            }
        }
    )
