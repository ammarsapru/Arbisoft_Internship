from pydantic import BaseModel, ConfigDict

from fin_analyst.mcp_server.schemas.common import TickerSymbol


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanyReference(Domain):
    company_name: str
    ticker: TickerSymbol
    exchange: str


class TopCompaniesList(Domain):
    """A curated, static reference list - NOT a live market-cap ranking.
    This app has no data source that ranks companies against each other
    (SerpApi's key_stats gives market cap per ticker only once you already
    know which ticker to query, not a cross-company leaderboard), so this
    is a fixed list of well-known large-cap companies maintained by hand,
    disclosed as such rather than presented as authoritative or current."""

    companies: list[CompanyReference]
    note: str = (
        "Static curated list of well-known large-cap companies, not a live-ranked "
        "top-20-by-market-cap - this server has no data source for cross-company ranking."
    )
