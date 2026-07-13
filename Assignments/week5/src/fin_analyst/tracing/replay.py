"""CLI: pretty-print / replay a trace run.

    uv run python -m fin_analyst.tracing.replay <run_id>
"""

import sys

from rich.console import Console
from rich.table import Table

from fin_analyst.tracing.tracer import load_run_events, summarize_run_cost

console = Console()

_LAYER_STYLE = {"mcp_tool": "cyan", "agent_node": "yellow", "llm_call": "magenta"}


def replay(run_id: str) -> None:
    events = load_run_events(run_id)
    if not events:
        console.print(f"[red]No trace events found for run_id={run_id}[/red]")
        return

    table = Table(title=f"Trace replay: {run_id}", show_lines=False)
    table.add_column("t+ms", justify="right")
    table.add_column("layer")
    table.add_column("actor")
    table.add_column("status")
    table.add_column("latency_ms", justify="right")
    table.add_column("tokens (in/out)")

    t0 = events[0].timestamp
    for e in events:
        offset_ms = (e.timestamp - t0).total_seconds() * 1000
        status_style = "green" if e.status == "ok" else "bold red"
        tokens = f"{e.input_tokens or '-'}/{e.output_tokens or '-'}" if e.layer == "llm_call" else "-"
        table.add_row(
            f"{offset_ms:,.0f}",
            f"[{_LAYER_STYLE.get(e.layer, 'white')}]{e.layer}[/]",
            e.actor,
            f"[{status_style}]{e.status}[/]",
            f"{e.latency_ms:,.0f}",
            tokens,
        )
        if e.status == "error":
            console.print(f"  [bold red]-> {e.error_detail}[/bold red]")

    console.print(table)

    summary = summarize_run_cost(run_id)
    console.print(
        f"\n[bold]Summary[/bold]: {summary['total_events']} events "
        f"({summary['mcp_tool_calls']} MCP tool, {summary['agent_node_calls']} agent-node, {summary['llm_calls']} LLM calls) | "
        f"tokens in={summary['total_input_tokens']:,} out={summary['total_output_tokens']:,} | "
        f"est. cost=${summary['estimated_cost_usd']:.4f} | "
        f"wall latency sum={summary['total_latency_ms']:,.0f}ms"
    )
    if summary["errors"]:
        console.print(f"[bold red]{len(summary['errors'])} error(s) in this run[/bold red]")


def main() -> None:
    if len(sys.argv) < 2:
        console.print("Usage: python -m fin_analyst.tracing.replay <run_id>")
        sys.exit(1)
    replay(sys.argv[1])


if __name__ == "__main__":
    main()
