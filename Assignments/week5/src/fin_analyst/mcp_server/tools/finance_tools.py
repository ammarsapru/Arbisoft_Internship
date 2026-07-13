"""Finance tools — resolve_ticker, get_market_snapshot, get_stock_financials.

Behavior below is calibrated against LIVE SerpApi responses (2026-07-09), not
just the published docs, which turned out to be incomplete on two points:

1. `engine=google_finance` REJECTS plain company names outright ("hasn't
   returned any results") — there is no fuzzy name matching and no
   `suggestions` fallback for a bare name. So a direct google_finance lookup
   only works if the caller already has a `TICKER:EXCHANGE` string; for a
   free-text company name, the web-search fallback (engine=google) is the
   only viable path, not a secondary one as originally assumed.
2. `engine=google_finance` returns a DIFFERENT subset of fields depending on
   whether `window` is passed: window-less calls return `knowledge_graph` +
   `financials` + embedded `news_results`, windowed calls return only
   `graph` + `summary`. get_stock_financials therefore always makes two
   SerpApi calls internally (both benefit from the client's TTL cache).
"""

import re
from datetime import datetime, timezone

from fin_analyst.mcp_server.clients.serpapi_client import SerpApiError, get_serpapi_client
from fin_analyst.mcp_server.schemas.common import FinanceWindow, parse_numeric
from fin_analyst.mcp_server.schemas.finance import (
    CompanyProfile,
    FinancialBundle,
    FinancialStatement,
    KeyStat,
    MarketSnapshot,
    PeriodRequest,
    PriceHistoryPoint,
    RelativePerformance,
    StockSummary,
    TechnicalIndicators,
)
from fin_analyst.mcp_server.schemas.raw.finance import RawGoogleFinanceResponse, RawMarketsResponse
from fin_analyst.mcp_server.schemas.report import (
    Ambiguous,
    LookupFailed,
    NotPubliclyListed,
    Resolved,
    ResolveTickerResult,
)

_TICKER_EXCHANGE_RE = re.compile(r"^[A-Z0-9.\-]+:[A-Z]+$")
_KG_TYPE_RE = re.compile(r"^([A-Za-z .]+):\s*([A-Z0-9.\-]+)$")

## (benchmark display name, stable Google Finance index code) per exchange.
## Hardcoded rather than discovered via get_market_snapshot(): live testing
## found that engine=google_finance_markets can stop returning its `markets`
## object entirely (observed mid-session, reproduced 3x, not a caching
## artifact - a real third-party behavior change, not a bug here) while the
## index tickers themselves remain reliably queryable via the same
## engine=google_finance path used for stocks. Hardcoding removes relative
## performance's dependency on that fragile listing endpoint.
_HOME_INDEX_BY_EXCHANGE = {
    "NASDAQ": ("Nasdaq", ".IXIC:INDEXNASDAQ"),
    "NYSE": ("S&P 500", ".INX:INDEXSP"),
    "NYSEAMERICAN": ("S&P 500", ".INX:INDEXSP"),
    "AMEX": ("S&P 500", ".INX:INDEXSP"),
}


async def _verify_ticker(ticker_exchange: str) -> RawGoogleFinanceResponse | None:
    client = get_serpapi_client()
    try:
        data = await client.search("google_finance", q=ticker_exchange, hl="en")
    except SerpApiError:
        return None
    parsed = RawGoogleFinanceResponse.model_validate(data)
    if parsed.summary is None or parsed.summary.stock is None:
        return None
    return parsed


def _title_overlap_confidence(query: str, resolved_title: str) -> str:
    query_words = {w.lower() for w in re.findall(r"[A-Za-z]+", query) if len(w) > 2}
    title_words = {w.lower() for w in re.findall(r"[A-Za-z]+", resolved_title) if len(w) > 2}
    if not query_words:
        return "medium"
    overlap = len(query_words & title_words) / len(query_words)
    if overlap >= 0.5:
        return "high"
    if overlap > 0:
        return "medium"
    return "low"


async def resolve_ticker(company_name: str) -> ResolveTickerResult:
    """Resolve a free-text company name (or an already-known TICKER:EXCHANGE
    string) to a verified, tradeable ticker.

    Two-stage internal lookup (see module docstring for why the order is
    what it is):
      1. If the input already looks like "TICKER:EXCHANGE", verify it
         directly against google_finance.
      2. Otherwise, use SerpApi's `google` web-search engine to find the
         company's ticker via Google's knowledge panel (query pattern:
         "{company_name} stock ticker"), then VERIFY that candidate against
         google_finance before trusting it — a knowledge-panel hit is a
         strong signal but not proof the ticker is actually tradeable.

    Returns a discriminated union, never raises for "not found" cases:
      - Resolved: a verified ticker, with `confidence` reflecting how well
        the resolved company name matches what was asked for.
      - NotPubliclyListed: no ticker found at all — the strongest signal
        this project has for "this company is private."
      - Ambiguous: reserved for future multi-candidate disambiguation.
      - LookupFailed: a candidate was found but failed verification, or the
        SerpApi call itself errored (network/quota) — distinct from
        NotPubliclyListed because retrying might succeed.
    """
    query = company_name.strip()
    normalized = query.upper()

    if _TICKER_EXCHANGE_RE.match(normalized):
        verified = await _verify_ticker(normalized)
        if verified is None:
            return LookupFailed(query=query, reason=f"'{normalized}' is not a recognized ticker:exchange pair on Google Finance.")
        return Resolved(
            ticker=verified.summary.stock,
            exchange=verified.summary.exchange or "UNKNOWN",
            display_name=verified.summary.title or verified.summary.stock,
            confidence="high",
            resolved_via="google_finance",
        )

    client = get_serpapi_client()
    try:
        ws_data = await client.search("google", q=f"{query} stock ticker", hl="en", gl="us")
    except SerpApiError as exc:
        return LookupFailed(query=query, reason=f"Web search lookup failed: {exc}")

    kg = ws_data.get("knowledge_graph") or {}
    kg_type = kg.get("type")
    if not kg_type:
        return NotPubliclyListed(
            query=query,
            reason="No stock ticker found in Google's knowledge panel for this company - it is most likely not publicly traded.",
        )

    match = _KG_TYPE_RE.match(kg_type)
    if not match:
        return LookupFailed(query=query, reason=f"Found a knowledge panel but couldn't parse its exchange/ticker format: {kg_type!r}")

    exchange_raw, ticker = match.groups()
    candidate = f"{ticker.strip().upper()}:{exchange_raw.strip().upper()}"

    verified = await _verify_ticker(candidate)
    if verified is None:
        return LookupFailed(
            query=query,
            reason=f"Web search suggested {candidate} for '{query}' but Google Finance has no data for that ticker.",
        )

    resolved_title = verified.summary.title or verified.summary.stock
    confidence = _title_overlap_confidence(query, resolved_title)

    return Resolved(
        ticker=verified.summary.stock,
        exchange=verified.summary.exchange or exchange_raw.strip().upper(),
        display_name=resolved_title,
        confidence=confidence,
        resolved_via="web_search",
    )


async def get_market_snapshot() -> MarketSnapshot:
    """Fetch current regional index snapshots (US, Europe, Asia) from Google
    Finance Markets — used for index-relative performance comparison."""
    client = get_serpapi_client()
    data = await client.search("google_finance_markets", trend="indexes", hl="en", gl="us")
    raw = RawMarketsResponse.model_validate(data)
    return MarketSnapshot.from_raw(raw)


def _home_index_for_exchange(exchange: str) -> tuple[str, str]:
    return _HOME_INDEX_BY_EXCHANGE.get(exchange.upper(), ("S&P 500", ".INX:INDEXSP"))


async def _fetch_benchmark_period_return(client, index_code: str, window: FinanceWindow) -> float | None:
    """Fetches the benchmark INDEX's own price history over the SAME window
    as the stock being analyzed, and computes its period return the same
    way TechnicalIndicators does for the stock.

    Bug this fixes: naively using a snapshot's "today's movement" as "the
    benchmark's period return" compared a stock's multi-year return against
    the index's single-day move whenever window != "1D" - a real, silent
    mismatch, not visibly wrong in the output since both are just
    percentages. Index tickers (e.g. ".IXIC:INDEXNASDAQ") are themselves
    valid google_finance queries, so we fetch the index's windowed graph
    exactly like get_stock_financials does for the stock, rather than
    relying on any snapshot/listing endpoint at all.
    """
    try:
        data = await client.search("google_finance", q=index_code, hl="en", window=window)
    except SerpApiError:
        return None
    raw = RawGoogleFinanceResponse.model_validate(data)
    price_history = sorted(
        (p for raw_point in raw.graph if (p := PriceHistoryPoint.from_raw(raw_point)) is not None),
        key=lambda p: p.date,
    )
    return TechnicalIndicators.from_history(price_history).period_return_pct


async def get_stock_financials(
    ticker: str,
    exchange: str,
    company_name: str,
    window: FinanceWindow,
    requested_period_text: str | None = None,
    period_caveat: str | None = None,
) -> FinancialBundle:
    """Fetch a company's summary, price history, valuation stats, and
    financial statements from Google Finance.

    `window` must be one of "1D","5D","1M","6M","YTD","1Y","5Y","MAX" — this
    is a closed enum because that is the complete set Google Finance
    actually supports (see docs/05-tool-design-for-agents.md); there is no
    arbitrary custom date range. Internally issues two SerpApi calls (a
    window-less call for fundamentals + a windowed call for the price
    series) because Google Finance splits that data across the two response
    shapes — see the module docstring.
    """
    client = get_serpapi_client()
    ticker_exchange = f"{ticker}:{exchange}"

    fundamentals_data = await client.search("google_finance", q=ticker_exchange, hl="en", gl="us")
    fundamentals = RawGoogleFinanceResponse.model_validate(fundamentals_data)

    windowed_data = await client.search("google_finance", q=ticker_exchange, hl="en", window=window)
    windowed = RawGoogleFinanceResponse.model_validate(windowed_data)

    summary = StockSummary.from_raw(windowed.summary or fundamentals.summary)
    if summary is None:
        raise ValueError(f"Google Finance returned no summary data for {ticker_exchange}")

    price_history = sorted(
        (p for raw_point in windowed.graph if (p := PriceHistoryPoint.from_raw(raw_point)) is not None),
        key=lambda p: p.date,
    )
    technicals = TechnicalIndicators.from_history(price_history)

    key_stats = []
    if fundamentals.knowledge_graph and fundamentals.knowledge_graph.key_stats:
        for stat in fundamentals.knowledge_graph.key_stats.stats:
            if stat.label:
                key_stats.append(KeyStat(label=stat.label, raw_value=stat.value or "", parsed_value=parse_numeric(stat.value)))

    profile_description = None
    if fundamentals.knowledge_graph:
        for block in fundamentals.knowledge_graph.about:
            if block.description:
                profile_description = (
                    block.description.snippet if hasattr(block.description, "snippet") else str(block.description)
                )
                break

    statements = [FinancialStatement.from_raw(stmt) for stmt in fundamentals.financials]

    relative_performance = None
    if technicals.period_return_pct is not None:
        benchmark_name, benchmark_code = _home_index_for_exchange(summary.exchange)
        benchmark_period_return = await _fetch_benchmark_period_return(client, benchmark_code, window)
        if benchmark_period_return is not None:
            relative_performance = RelativePerformance(
                benchmark_name=benchmark_name,
                benchmark_period_return_pct=benchmark_period_return,
                stock_period_return_pct=technicals.period_return_pct,
            )

    return FinancialBundle(
        ticker=summary.ticker,
        company_name=company_name,
        period=PeriodRequest(raw_text=requested_period_text, resolved_window=window, caveat=period_caveat),
        summary=summary,
        price_history=price_history,
        technicals=technicals,
        key_stats=key_stats,
        profile=CompanyProfile(description=profile_description),
        statements=statements,
        relative_performance=relative_performance,
    )
