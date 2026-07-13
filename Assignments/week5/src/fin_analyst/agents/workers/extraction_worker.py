"""Worker A: Financial Data Extraction.

Deliberately makes NO LLM call - resolving a ticker and fetching financial
data given a validated company query is fully mechanical tool orchestration
(see docs/07-cost-latency-strategy.md: match model strength to task
difficulty, and zero strength is warranted when a task is this
deterministic). Tool calls still go through LangChain's StructuredTool
interface (client-side arg validation) and are traced as mcp_tool events.
"""

from fin_analyst.agents.mcp_tools import call_get_stock_financials, call_resolve_ticker
from fin_analyst.agents.period import parse_period
from fin_analyst.agents.state import PipelineState
from fin_analyst.mcp_server.schemas.report import ValidationFailure


async def run_extraction_worker(state: PipelineState, tools_by_name: dict) -> dict:
    ticker_result = await call_resolve_ticker(tools_by_name, state.company_query)

    if ticker_result.outcome != "resolved":
        reason = getattr(ticker_result, "reason", "Ticker could not be resolved.")
        return {
            "ticker_result": ticker_result,
            "validation_failures": [
                ValidationFailure(
                    stage="ticker_resolution",
                    reason=reason,
                    is_recoverable=(ticker_result.outcome == "failed"),
                )
            ],
            "next_step": "aborted",
            "final_message": f"Could not produce a report for '{state.company_query}': {reason}",
        }

    window, caveat = parse_period(state.period_query)

    # get_stock_financials fetches its own market snapshot server-side for
    # relative-performance comparison, so this worker doesn't need a
    # separate call - see mcp_server/tools/finance_tools.py.
    financial_bundle = await call_get_stock_financials(
        tools_by_name,
        ticker=ticker_result.ticker,
        exchange=ticker_result.exchange,
        company_name=ticker_result.display_name,
        window=window,
        requested_period_text=state.period_query,
        period_caveat=caveat,
    )

    return {"ticker_result": ticker_result, "financial_bundle": financial_bundle}
