"""Worker C: Report Formatting.

Excel construction is deterministic Python (WorkbookBuilder); the only LLM
call is a single fast-tier generation of the executive summary narrative -
a genuinely generative task, unlike Worker A's pure tool orchestration.
"""

from datetime import datetime, timezone
from pathlib import Path

from fin_analyst.agents.models import get_fast_model
from fin_analyst.agents.prompts import FORMATTING_WORKER_SYSTEM_PROMPT
from fin_analyst.agents.state import PipelineState
from fin_analyst.config import get_settings
from fin_analyst.mcp_server.schemas.report import ReportOutput, ValidationFailure
from fin_analyst.output.excel_builder import SHEET_NAMES, WorkbookBuilder


async def run_formatting_worker(state: PipelineState, tools_by_name: dict) -> dict:
    del tools_by_name
    bundle = state.financial_bundle
    news = state.news_impact_bundle

    if state.output_directory is not None and not Path(state.output_directory).is_absolute():
        reason = (
            f"output_directory must be an absolute path; got a relative path "
            f"('{state.output_directory}'), which would resolve against this server's own "
            f"working directory rather than the caller's - refusing rather than silently "
            f"writing to the wrong place."
        )
        return {
            "validation_failures": [ValidationFailure(stage="report_formatting", reason=reason, is_recoverable=True)],
            "next_step": "aborted",
            "final_message": reason,
        }

    news_section = "No news impact data was available." if not news or not news.scores else (
        f"{news.articles_considered} recent articles analyzed, aggregate impact score "
        f"{news.aggregate_impact_score:.2f}" if news.aggregate_impact_score is not None else "News analyzed."
    )

    prompt = (
        f"Company: {bundle.company_name} ({bundle.ticker}:{bundle.summary.exchange})\n"
        f"Current price: {bundle.summary.currency} {bundle.summary.price:.2f}, "
        f"movement: {bundle.summary.price_movement.direction if bundle.summary.price_movement else 'n/a'} "
        f"{bundle.summary.price_movement.percentage if bundle.summary.price_movement else 0:.2f}%\n"
        f"Analyzed period: {bundle.period.resolved_window} (user asked for: {bundle.period.raw_text or 'default'})"
        f"{' - caveat: ' + bundle.period.caveat if bundle.period.caveat else ''}\n"
        f"Period return: {bundle.technicals.period_return_pct}\n"
        f"Volatility %: {bundle.technicals.volatility_pct}\n"
        f"Max drawdown %: {bundle.technicals.max_drawdown_pct}\n"
        f"Net margin %: {bundle.net_margin_pct}\n"
        f"Relative performance: {bundle.relative_performance}\n"
        f"News: {news_section}\n"
    )

    model = get_fast_model(max_tokens=512)
    response = await model.ainvoke([("system", FORMATTING_WORKER_SYSTEM_PROMPT), ("human", prompt)])
    executive_summary = response.content if isinstance(response.content, str) else str(response.content)

    settings = get_settings()
    output_dir = Path(state.output_directory) if state.output_directory is not None else settings.report_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{bundle.ticker}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.xlsx"
    output_path = output_dir / file_name

    builder = WorkbookBuilder(output_path, bundle, news, executive_summary)
    builder.build()

    report_output = ReportOutput(
        file_path=str(output_path),
        ticker=bundle.ticker,
        company_name=bundle.company_name,
        executive_summary=executive_summary,
        sheet_names=SHEET_NAMES,
    )
    return {"report_output": report_output, "next_step": "done", "final_message": executive_summary}
