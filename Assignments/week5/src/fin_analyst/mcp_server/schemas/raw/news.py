from pydantic import BaseModel, ConfigDict


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawNewsSource(_Lenient):
    name: str | None = None


class RawNewsResult(_Lenient):
    """engine=google_news result item — confirmed to include iso_date,
    unlike the embedded news_results on the google_finance response."""

    title: str | None = None
    link: str | None = None
    source: RawNewsSource | str | None = None
    date: str | None = None
    iso_date: str | None = None
    snippet: str | None = None
    thumbnail: str | None = None


class RawGoogleNewsResponse(_Lenient):
    news_results: list[RawNewsResult] = []


class RawKnowledgeGraphEntity(_Lenient):
    """engine=google (web search) knowledge graph — used as the ticker
    resolution fallback. `type` carries "EXCHANGE: TICKER" for a publicly
    traded entity, e.g. "NASDAQ: TSLA" (confirmed live)."""

    title: str | None = None
    type: str | None = None
    entity_type: str | None = None


class RawWebSearchResponse(_Lenient):
    knowledge_graph: RawKnowledgeGraphEntity | None = None
