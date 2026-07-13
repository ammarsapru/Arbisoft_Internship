import statistics
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from fin_analyst.mcp_server.schemas.common import (
    Direction,
    FinanceWindow,
    Percentage,
    TickerSymbol,
    parse_flexible_datetime,
    parse_numeric,
)
from fin_analyst.mcp_server.schemas.raw.finance import (
    RawFinancialPeriod,
    RawFinancialStatement,
    RawGoogleFinanceResponse,
    RawGraphPoint,
    RawMarketAsset,
    RawMarketsResponse,
    RawSummary,
)


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriceMovement(Domain):
    percentage: Percentage
    value: float
    direction: Direction

    @model_validator(mode="after")
    def _consistent_sign(self) -> "PriceMovement":
        if self.direction == "Down" and self.value > 0:
            self.value = -self.value
        return self

    @classmethod
    def from_raw(cls, raw) -> "PriceMovement | None":
        if raw is None or raw.percentage is None or raw.value is None:
            return None
        movement = raw.movement if raw.movement in ("Up", "Down") else "Flat"
        return cls(percentage=raw.percentage, value=raw.value, direction=movement)


class StockSummary(Domain):
    title: str
    ticker: TickerSymbol
    exchange: str
    currency: str
    price: float
    price_movement: PriceMovement | None
    as_of: str
    after_hours_price: float | None = None
    after_hours_movement: PriceMovement | None = None

    @classmethod
    def from_raw(cls, raw: RawSummary | None) -> "StockSummary | None":
        if raw is None or raw.stock is None or raw.extracted_price is None:
            return None
        return cls(
            title=raw.title or raw.stock,
            ticker=raw.stock,
            exchange=raw.exchange or "UNKNOWN",
            currency=raw.currency or "USD",
            price=raw.extracted_price,
            price_movement=PriceMovement.from_raw(raw.price_movement),
            as_of=raw.date or "",
            after_hours_price=raw.market.extracted_price if raw.market else None,
            after_hours_movement=PriceMovement.from_raw(raw.market.price_movement) if raw.market else None,
        )


class PriceHistoryPoint(Domain):
    date: datetime
    price: float
    volume: int | None = None
    is_key_event: bool = False

    @classmethod
    def from_raw(cls, raw: RawGraphPoint) -> "PriceHistoryPoint | None":
        if raw.price is None or not raw.date:
            return None
        return cls(
            date=parse_flexible_datetime(raw.date),
            price=raw.price,
            volume=raw.volume,
            is_key_event=raw.key_event is not None,
        )


class KeyStat(Domain):
    label: str
    raw_value: str
    parsed_value: float | None = None


class CompanyProfile(Domain):
    description: str | None = None


class FinancialLineItem(Domain):
    title: str
    raw_value: str | None
    parsed_value: float | None
    change_pct: float | None


class FinancialStatementPeriod(Domain):
    period_label: str
    period_type: str
    line_items: list[FinancialLineItem]

    def get(self, title: str) -> FinancialLineItem | None:
        needle = title.lower()
        for item in self.line_items:
            if item.title.lower() == needle:
                return item
        return None


class FinancialStatement(Domain):
    statement_name: str
    periods: list[FinancialStatementPeriod]

    @classmethod
    def from_raw(cls, raw: RawFinancialStatement) -> "FinancialStatement":
        periods = []
        for period in raw.results:
            items = [
                FinancialLineItem(
                    title=item.title or "Unknown",
                    raw_value=item.value,
                    parsed_value=parse_numeric(item.value),
                    change_pct=parse_numeric(item.change),
                )
                for item in period.table
                if item.title
            ]
            periods.append(
                FinancialStatementPeriod(
                    period_label=period.date or "Unknown",
                    period_type=period.period_type or "Unknown",
                    line_items=items,
                )
            )
        return cls(statement_name=raw.title or "Unknown", periods=periods)


class TechnicalIndicators(Domain):
    """Computed client-side from the price graph — Google Finance has no
    technicals endpoint of its own. See docs/07 for why this is worth
    computing rather than shipping raw prices only."""

    period_return_pct: float | None
    volatility_pct: float | None
    max_drawdown_pct: float | None
    sma_20: float | None
    ema_20: float | None

    @classmethod
    def from_history(cls, points: list[PriceHistoryPoint]) -> "TechnicalIndicators":
        if len(points) < 2:
            return cls(period_return_pct=None, volatility_pct=None, max_drawdown_pct=None, sma_20=None, ema_20=None)

        ordered = sorted(points, key=lambda p: p.date)
        prices = [p.price for p in ordered]

        period_return = (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] else None

        daily_returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1]
        ]
        volatility = statistics.pstdev(daily_returns) * 100 if len(daily_returns) > 1 else None

        peak = prices[0]
        max_dd = 0.0
        for p in prices:
            peak = max(peak, p)
            if peak:
                max_dd = min(max_dd, (p - peak) / peak * 100)

        sma_window = prices[-20:]
        sma_20 = sum(sma_window) / len(sma_window) if sma_window else None

        ema_20 = None
        if len(prices) >= 1:
            k = 2 / (min(20, len(prices)) + 1)
            ema_20 = prices[0]
            for p in prices[1:]:
                ema_20 = p * k + ema_20 * (1 - k)

        return cls(
            period_return_pct=period_return,
            volatility_pct=volatility,
            max_drawdown_pct=max_dd if daily_returns else None,
            sma_20=sma_20,
            ema_20=ema_20,
        )


class MarketIndex(Domain):
    code: str
    name: str
    price: float
    price_movement: PriceMovement | None

    @classmethod
    def from_raw(cls, raw: RawMarketAsset) -> "MarketIndex | None":
        if raw.stock is None or raw.price is None:
            return None
        return cls(code=raw.stock, name=raw.name or raw.stock, price=raw.price, price_movement=PriceMovement.from_raw(raw.price_movement))


class MarketSnapshot(Domain):
    region_indexes: dict[str, list[MarketIndex]]

    @classmethod
    def from_raw(cls, raw: RawMarketsResponse) -> "MarketSnapshot":
        region_indexes: dict[str, list[MarketIndex]] = {}
        for region, assets in raw.markets.items():
            parsed = [idx for a in assets if (idx := MarketIndex.from_raw(a)) is not None]
            if parsed:
                region_indexes[region] = parsed
        return cls(region_indexes=region_indexes)

    def find(self, name_contains: str) -> MarketIndex | None:
        needle = name_contains.lower()
        for indexes in self.region_indexes.values():
            for idx in indexes:
                if needle in idx.name.lower():
                    return idx
        return None


class RelativePerformance(Domain):
    """NOTE: outperformance_pct is a stored field set by a model_validator,
    not a @computed_field - live testing found that FastMCP's output-schema
    validation (built from pydantic's default *validation*-mode JSON
    Schema) excludes computed fields from `properties`, which combined with
    this project's extra="forbid" models makes any @computed_field on a
    type nested inside an MCP tool's return value fail with an
    "Additional properties are not allowed" error. See
    docs/02-building-mcp-servers.md."""

    benchmark_name: str
    benchmark_period_return_pct: float | None
    stock_period_return_pct: float | None
    outperformance_pct: float | None = None

    @model_validator(mode="after")
    def _compute_outperformance(self) -> "RelativePerformance":
        if self.benchmark_period_return_pct is not None and self.stock_period_return_pct is not None:
            self.outperformance_pct = self.stock_period_return_pct - self.benchmark_period_return_pct
        return self


class PeriodRequest(Domain):
    """See docs/... 'Current snapshot vs user-defined historical period' —
    the raw ask is always preserved alongside the resolved enum + caveat so
    the report can be transparent about what was actually used."""

    raw_text: str | None
    resolved_window: FinanceWindow
    caveat: str | None = None


class FinancialBundle(Domain):
    ticker: TickerSymbol
    company_name: str
    period: PeriodRequest
    summary: StockSummary
    price_history: list[PriceHistoryPoint]
    technicals: TechnicalIndicators
    key_stats: list[KeyStat]
    profile: CompanyProfile
    statements: list[FinancialStatement]
    relative_performance: RelativePerformance | None = None
    net_margin_pct: float | None = None

    @model_validator(mode="after")
    def _compute_net_margin(self) -> "FinancialBundle":
        if self.net_margin_pct is not None:
            return self
        income_stmt = next((s for s in self.statements if s.statement_name.lower() == "income statement"), None)
        if not income_stmt or not income_stmt.periods:
            return self
        latest = income_stmt.periods[0]
        revenue = latest.get("Revenue")
        net_income = latest.get("Net income")
        if revenue and net_income and revenue.parsed_value and net_income.parsed_value is not None:
            self.net_margin_pct = net_income.parsed_value / revenue.parsed_value * 100
        return self
