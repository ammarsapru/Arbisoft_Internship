from datetime import datetime, timezone

from fin_analyst.mcp_server.schemas.finance import FinancialBundle
from fin_analyst.mcp_server.schemas.report import CompanyReportBundle

_report_cache: dict[str, CompanyReportBundle] = {}


def cache_financial_bundle(bundle: FinancialBundle) -> None:
    """Called by the get_stock_financials tool after it computes a
    FinancialBundle, so the finance-report://{ticker} resource has
    something to read without making its own live API call. Per
    docs/02-building-mcp-servers.md: tools fetch and compute, resources
    expose what's already been computed."""
    _report_cache[bundle.ticker] = CompanyReportBundle(
        ticker=bundle.ticker,
        company_name=bundle.company_name,
        financials=bundle,
        news_impact=None,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def get_cached_report(ticker: str) -> CompanyReportBundle | None:
    return _report_cache.get(ticker.upper())
