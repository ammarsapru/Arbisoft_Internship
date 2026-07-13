from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, computed_field

from fin_analyst.mcp_server.schemas.common import Magnitude, Sentiment, parse_flexible_datetime
from fin_analyst.mcp_server.schemas.raw.news import RawNewsResult


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewsArticle(Domain):
    title: str
    link: str
    source: str
    published_at: datetime
    snippet: str | None = None

    @classmethod
    def from_raw(cls, raw: RawNewsResult) -> "NewsArticle | None":
        if not raw.title or not raw.link:
            return None
        source_name = raw.source.name if hasattr(raw.source, "name") else (raw.source or "Unknown")
        timestamp_source = raw.iso_date or raw.date
        if not timestamp_source:
            return None
        return cls(
            title=raw.title,
            link=raw.link,
            source=source_name or "Unknown",
            published_at=parse_flexible_datetime(timestamp_source),
            snippet=raw.snippet,
        )


_SENTIMENT_SIGN = {"positive": 1, "negative": -1, "neutral": 0}


class NewsImpactScore(Domain):
    """LLM-produced structured output (see docs/08) — sentiment + magnitude
    are the model's judgment; recency_weight is computed deterministically
    from published_at vs. last close, not left to the model."""

    article_title: str
    article_link: str
    sentiment: Sentiment
    magnitude: Magnitude
    rationale: str
    recency_weight: float

    @computed_field
    @property
    def composite_score(self) -> float:
        return _SENTIMENT_SIGN[self.sentiment] * self.magnitude * self.recency_weight


def compute_recency_weight(published_at: datetime, reference: datetime, half_life_hours: float = 48.0) -> float:
    """Exponential decay: news at the reference time = weight 1.0, halving
    every `half_life_hours`. Future-dated articles (clock skew) clamp to 1.0."""
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    hours_elapsed = max(0.0, (reference - published_at).total_seconds() / 3600.0)
    return 0.5 ** (hours_elapsed / half_life_hours)


class NewsImpactBundle(Domain):
    ticker: str
    reference_close_time: datetime
    articles_considered: int
    scores: list[NewsImpactScore]

    @computed_field
    @property
    def aggregate_impact_score(self) -> float | None:
        if not self.scores:
            return None
        total_weight = sum(s.recency_weight for s in self.scores) or 1.0
        return sum(s.composite_score for s in self.scores) / total_weight
