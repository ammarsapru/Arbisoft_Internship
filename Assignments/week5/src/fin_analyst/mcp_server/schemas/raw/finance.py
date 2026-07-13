"""Raw (loosely-typed, extra=ignore) models mirroring live SerpApi JSON shapes.

Confirmed against real API responses (google_finance, google_finance_markets)
on 2026-07-09 — see docs/02-building-mcp-servers.md. These models' only job is
"don't crash on a live response"; mapping to strict domain models happens in
schemas/finance.py.
"""

from pydantic import BaseModel, ConfigDict


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawPriceMovement(_Lenient):
    percentage: float | None = None
    value: float | None = None
    movement: str | None = None


class RawGraphPoint(_Lenient):
    price: float | None = None
    currency: str | None = None
    date: str | None = None
    volume: int | None = None
    key_event: dict | None = None


class RawMarketBlock(_Lenient):
    price: str | None = None
    extracted_price: float | None = None
    currency: str | None = None
    price_movement: RawPriceMovement | None = None


class RawSummary(_Lenient):
    title: str | None = None
    stock: str | None = None
    exchange: str | None = None
    price: str | None = None
    extracted_price: float | None = None
    currency: str | None = None
    price_movement: RawPriceMovement | None = None
    date: str | None = None
    market: RawMarketBlock | None = None


class RawKeyStatItem(_Lenient):
    label: str | None = None
    value: str | None = None


class RawKeyStats(_Lenient):
    stats: list[RawKeyStatItem] = []


class RawAboutDescription(_Lenient):
    snippet: str | None = None


class RawAboutBlock(_Lenient):
    title: str | None = None
    description: RawAboutDescription | str | None = None


class RawKnowledgeGraph(_Lenient):
    key_stats: RawKeyStats | None = None
    about: list[RawAboutBlock] = []


class RawFinancialLineItem(_Lenient):
    title: str | None = None
    value: str | None = None
    change: str | None = None


class RawFinancialPeriod(_Lenient):
    date: str | None = None
    period_type: str | None = None
    table: list[RawFinancialLineItem] = []


class RawFinancialStatement(_Lenient):
    title: str | None = None
    results: list[RawFinancialPeriod] = []


class RawEmbeddedNewsResult(_Lenient):
    snippet: str | None = None
    link: str | None = None
    source: str | None = None
    date: str | None = None
    thumbnail: str | None = None


class RawGoogleFinanceResponse(_Lenient):
    """Response shape for engine=google_finance.

    IMPORTANT (empirically confirmed): when `window` is passed, SerpApi
    returns only `graph` + `summary`. `knowledge_graph`, `financials`,
    `news_results`, and `discover_more` are only populated on the
    window-less (default) call. `get_stock_financials` therefore always
    makes two calls internally — see docs/05-tool-design-for-agents.md.
    """

    graph: list[RawGraphPoint] = []
    summary: RawSummary | None = None
    knowledge_graph: RawKnowledgeGraph | None = None
    financials: list[RawFinancialStatement] = []
    news_results: list[RawEmbeddedNewsResult] = []


class RawMarketAsset(_Lenient):
    stock: str | None = None
    name: str | None = None
    price: float | None = None
    price_movement: RawPriceMovement | None = None


class RawMarketsResponse(_Lenient):
    markets: dict[str, list[RawMarketAsset]] = {}
