import functools
from typing import Any, Callable

from fin_analyst.tracing.tracer import traced_call


def traced_tool(name: str):
    """Decorator wrapping an MCP tool implementation so every call is
    captured as a `mcp_tool`-layer TraceEvent, regardless of whether it was
    invoked from Claude Code or the agent's MultiServerMCPClient - see
    docs/06-agent-debugging.md."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any):
            with traced_call("mcp_tool", name, input_value=kwargs or args) as record:
                output = await fn(*args, **kwargs)
                record["output"] = output
                return output

        return wrapper

    return decorator
