"""Entrypoint for running the full pipeline end-to-end:

    uv run python -m fin_analyst.cli "Apple" --period "5 years"
"""

import argparse
import asyncio
from pathlib import Path

from rich.console import Console

from fin_analyst.agents.pipeline import run_pipeline
from fin_analyst.tracing.tracer import summarize_run_cost

console = Console()


async def _main(company: str, period: str | None, output_dir: str | None) -> None:
    console.print(f"[bold]Running financial analysis pipeline[/bold] for [cyan]{company}[/cyan] (period: {period or 'default'})...")
    # Resolve to an absolute path relative to *this shell's* cwd before
    # passing it on - run_pipeline requires an absolute path (see
    # agents/pipeline.py) since a relative one would otherwise be
    # ambiguous about which process's cwd it's relative to.
    absolute_output_dir = str(Path(output_dir).resolve()) if output_dir else None
    state, run_id = await run_pipeline(company, period, absolute_output_dir)

    console.print(f"\n[bold]run_id[/bold]: {run_id}")

    if state.report_output is not None:
        console.print(f"[bold green]Report generated[/bold green]: {state.report_output.file_path}")
        console.print(f"\n[bold]Executive summary[/bold]:\n{state.report_output.executive_summary}")
    else:
        console.print(f"[bold red]Pipeline did not complete a report.[/bold red]")
        if state.final_message:
            console.print(state.final_message)

    if state.validation_failures:
        console.print("\n[bold yellow]Validation failures encountered:[/bold yellow]")
        for f in state.validation_failures:
            console.print(f" - {f.stage}: {f.reason}")

    summary = summarize_run_cost(run_id)
    console.print(
        f"\n[bold]Cost/latency[/bold]: {summary['llm_calls']} LLM calls, "
        f"tokens in={summary['total_input_tokens']:,} out={summary['total_output_tokens']:,}, "
        f"est. cost=${summary['estimated_cost_usd']:.4f}, "
        f"{summary['mcp_tool_calls']} MCP tool calls, wall latency sum={summary['total_latency_ms']:,.0f}ms"
    )
    console.print(f"Replay with: uv run python -m fin_analyst.tracing.replay {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a financial analysis report for a company.")
    parser.add_argument("company", help="Company name, e.g. 'Apple' or 'Tesla Inc'")
    parser.add_argument("--period", default=None, help="Time period to analyze, e.g. '5 years', 'YTD', '1 month'")
    parser.add_argument("--output-dir", default=None, help="Directory to write the .xlsx report to (default: ./reports)")
    args = parser.parse_args()
    asyncio.run(_main(args.company, args.period, args.output_dir))


if __name__ == "__main__":
    main()
