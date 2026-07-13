"""FastMCP app entrypoint. Run standalone (e.g. via Claude Code) with:

    uv run python -m fin_analyst.mcp_server.server

When launched as a subprocess by the agent's MultiServerMCPClient, the
parent process sets the TRACE_RUN_ID env var so this server's tool-call
trace events land in the *same* JSONL file as the agent-layer events for
that pipeline run, unifying tracing across the process boundary - see
docs/06-agent-debugging.md.
"""

import os

from mcp.server.fastmcp import FastMCP

from fin_analyst.mcp_server.resources.report_resource import cache_financial_bundle, get_cached_report
from fin_analyst.mcp_server.resources.top_companies_resource import get_top_companies
from fin_analyst.mcp_server.prompts.analyst_prompt import financial_analyst_briefing as _financial_analyst_briefing
from fin_analyst.mcp_server.schemas.common import FinanceWindow
from fin_analyst.mcp_server.schemas.finance import FinancialBundle, MarketSnapshot
from fin_analyst.mcp_server.schemas.news import NewsArticle
from fin_analyst.mcp_server.schemas.reference import TopCompaniesList
from fin_analyst.mcp_server.schemas.report import (
    CompanyReportBundle,
    GenerateReportResult,
    ReportAborted,
    ReportGenerated,
    ResolveTickerResult,
)
from fin_analyst.mcp_server.tools import finance_tools, news_tools
from fin_analyst.tracing.mcp_middleware import traced_tool
from fin_analyst.tracing.tracer import new_run_id, run_context

mcp = FastMCP("financial-analyst")


@mcp.tool()
@traced_tool("resolve_ticker")
async def resolve_ticker(company_name: str) -> ResolveTickerResult:
    """Resolve a company name (e.g. "Apple", "Tesla Inc") to a verified
    stock ticker and exchange. Also accepts an already-known "TICKER:EXCHANGE"
    string (e.g. "AAPL:NASDAQ") and verifies it directly.

    Returns one of four outcomes (check the `outcome` field):
      - "resolved": ticker/exchange found and verified against live Google
        Finance data. `confidence` ("high"/"medium"/"low") reflects how well
        the resolved company name matches the query.
      - "not_listed": no ticker found at all - the company is most likely
        not publicly traded. This is an expected, valid outcome, not an
        error; do not retry.
      - "ambiguous": multiple plausible tickers found; check `candidates`.
      - "failed": a lookup or verification step errored; may be worth
        retrying (e.g. transient network/API issue).
    """
    return await finance_tools.resolve_ticker(company_name)


@mcp.tool()
@traced_tool("get_market_snapshot")
async def get_market_snapshot() -> MarketSnapshot:
    """Fetch current regional stock index snapshots (US: Dow/S&P/Nasdaq,
    Europe, Asia, etc.) from Google Finance Markets. Use this to compare a
    specific stock's performance against its home market."""
    return await finance_tools.get_market_snapshot()


@mcp.tool()
@traced_tool("get_stock_financials")
async def get_stock_financials(
    ticker: str,
    exchange: str,
    company_name: str,
    window: FinanceWindow,
    requested_period_text: str | None = None,
    period_caveat: str | None = None,
) -> FinancialBundle:
    """Fetch a verified company's current price summary, price history
    (with computed technicals: period return, volatility, max drawdown,
    SMA/EMA), valuation key stats, company profile, and financial statements
    (income statement / balance sheet / cash flow, quarterly and annual)
    from Google Finance.

    `window` MUST be exactly one of: "1D", "5D", "1M", "6M", "YTD", "1Y",
    "5Y", "MAX" - this is the complete set Google Finance supports; there is
    no arbitrary custom date range. If the user asked for a period outside
    this set (e.g. "10 years"), map it to the nearest supported window
    before calling this tool and pass the original ask as
    `requested_period_text` plus an explanation as `period_caveat` so the
    mismatch is preserved and surfaced in the final report rather than
    silently substituted.

    Only call this after `resolve_ticker` has returned a "resolved" outcome
    - `ticker` and `exchange` here must be the verified values from that
    result, not a raw guess.
    """
    bundle = await finance_tools.get_stock_financials(
        ticker, exchange, company_name, window, requested_period_text, period_caveat
    )
    cache_financial_bundle(bundle)
    return bundle


@mcp.tool()
@traced_tool("get_company_news")
async def get_company_news(ticker: str, company_name: str) -> list[NewsArticle]:
    """Fetch recent news coverage for a publicly listed company via Google
    News. Returns up to 15 articles with title, source, link, snippet, and
    a precise publication timestamp - intended as the input to a news
    sentiment/market-impact analysis, not as a final answer on its own."""
    return await news_tools.get_company_news(ticker, company_name)


@mcp.tool()
@traced_tool("generate_financial_report")
async def generate_financial_report(
    company_name: str, period: str | None = None, output_directory: str | None = None
) -> GenerateReportResult:
    """Run the FULL financial analysis pipeline for a company and produce an
    Excel report - this is the entire supervisor + 3-worker system
    (Financial Data Extraction -> News Impact Analyst -> Report Formatting)
    exposed as a single tool call, not just raw data access.

    `period` accepts free text (e.g. "5 years", "YTD", "1 month"); it is
    mapped to the nearest window Google Finance actually supports, with any
    mismatch surfaced in the report rather than silently substituted.

    `output_directory`: where to write the .xlsx file. This server's own
    working directory may not be the same as yours (e.g. if you were
    launched from a different project folder), and there is no ambient way
    for a tool call to know your current directory automatically - so if
    you (the calling assistant) know your own current working directory and
    the user would expect the report to land there, pass it here explicitly
    as an ABSOLUTE path. A relative path will be rejected (it would resolve
    against this server's own directory, not yours, and silently write to
    the wrong place). If omitted, the report is written to this server's
    own default reports directory instead.

    This call takes noticeably longer than the other tools (typically
    1-5 minutes) because it runs multiple LLM calls and several external API
    calls internally - it is not a fast lookup. It also spends real,
    metered API cost (see docs/07-cost-latency-strategy.md).

    Returns one of two outcomes (check `outcome`):
      - "generated": `report.file_path` points to the finished .xlsx on
        disk (only useful to a caller with filesystem access to this
        machine, e.g. Claude Code - not to a client without local file
        access), plus the executive summary text. `pipeline_run_id` can be
        replayed with `uv run python -m fin_analyst.tracing.replay
        <pipeline_run_id>` to see every internal tool/LLM call this run made.
      - "aborted": a supervisor validation gate stopped the pipeline before
        producing a report (e.g. the company is not publicly listed, a
        resolved ticker failed a semantic relevance check, or
        `output_directory` was given as a relative path) - an expected,
        typed outcome, not a tool error.
    """
    from fin_analyst.agents.pipeline import run_pipeline

    state, pipeline_run_id = await run_pipeline(company_name, period, output_directory)

    if state.financial_bundle is not None:
        # Bug fix: run_pipeline's internal MultiServerMCPClient calls
        # get_stock_financials through a SEPARATELY-SPAWNED child server
        # subprocess, which populates that child's own _report_cache, not
        # this (outer) process's - so finance-report://{ticker} was always
        # null after generate_financial_report despite the pipeline having
        # fetched the data. Caching it here directly, in the process that
        # actually serves the resource, closes that gap.
        cache_financial_bundle(state.financial_bundle)

    if state.report_output is not None:
        return ReportGenerated(pipeline_run_id=pipeline_run_id, report=state.report_output)

    last_failure = state.validation_failures[-1] if state.validation_failures else None
    return ReportAborted(
        pipeline_run_id=pipeline_run_id,
        stage=last_failure.stage if last_failure else "unknown",
        reason=last_failure.reason if last_failure else (state.final_message or "Pipeline did not produce a report."),
    )


@mcp.resource("finance-report://{ticker}")
def company_report(ticker: str) -> CompanyReportBundle | None:
    """The most recently computed financial report bundle for a ticker,
    cached from the last get_stock_financials call - reading this resource
    makes no live API calls. Returns null if get_stock_financials has not
    yet been called for this ticker in the current server session."""
    return get_cached_report(ticker)


@mcp.resource("top-companies://top20")
def top_companies() -> TopCompaniesList:
    """A static, hand-curated list of ~20 well-known large-cap companies
    and their verified ticker:exchange pairs. Available immediately, no
    tool call or API access needed to read it - unlike finance-report://,
    this is reference data baked into the server, not a cache of computed
    results. NOT a live market-cap ranking (this server has no data source
    for cross-company ranking) - see the `note` field on the returned data."""
    return get_top_companies()


@mcp.prompt()
def financial_analyst_briefing(company: str) -> str:
    """A ready-to-use system prompt framing the assistant as an expert
    financial analyst and stock broker for a given company. NOTE: per the
    MCP spec, prompts are surfaced by the host's UI for a human to select
    (e.g. a slash command) - they are not callable by the model itself. An
    autonomous agent that needs this text programmatically should use the
    get_analyst_prompt TOOL below instead, which returns identical content."""
    return _financial_analyst_briefing(company)


@mcp.tool()
@traced_tool("get_analyst_prompt")
async def get_analyst_prompt(company: str) -> str:
    """Returns the same 'expert financial analyst and stock broker' framing
    text as the financial_analyst_briefing PROMPT, but as a tool an agent
    can call directly. The prompt primitive only surfaces through a host's
    UI for human selection (e.g. a slash command) - it has no mechanism for
    a model to fetch it itself, so this tool exists specifically to make
    the same content reachable by an autonomous agent, not just a human."""
    return _financial_analyst_briefing(company)


def main() -> None:
    run_id = os.environ.get("TRACE_RUN_ID") or new_run_id("mcpserver")
    with run_context(run_id):
        mcp.run()


if __name__ == "__main__":
    main()
